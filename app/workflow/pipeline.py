"""舆情分析流水线 — 8 步异步分析的核心编排器。"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Callable

from app.agents.forecast_agent import ForecastAgent
from app.agents.opinion_agent import OpinionAgent
from app.agents.preprocess_agent import PreprocessAgent
from app.agents.report_agent import ReportAgent
from app.agents.risk_agent import RiskAgent
from app.agents.sentiment_agent import SentimentAgent
from app.common.config import settings
from app.common.constants import EXTERNAL_SEARCH_LIMIT, RISK_LEVEL_MAP, TREND_MAP
from app.data.external_bocha import ExternalBocha
from app.data.external_tavily import ExternalTavily
from app.data.fusion import DataFusionService
from app.data.mindspider_adapter import MindSpiderAdapter
from app.data.pg_repository import PgRepository
from app.llm.gateway import LLMGateway
from app.schemas.analysis import ForecastResult, OpinionSummary, RiskResult, SentimentItem
from app.schemas.doc import UnifiedDoc
from app.schemas.report import AgentStepLog, TopicReport
from app.storage.db import session_scope

logger = logging.getLogger(__name__)


def _verify_evidence_chain(
    docs: list[UnifiedDoc],
    sentiments: list[SentimentItem] | None = None,
    opinions: OpinionSummary | None = None,
    risk: RiskResult | None = None,
    forecast: ForecastResult | None = None,
) -> list[str]:
    """Verify that all evidence IDs trace back to actual UnifiedDoc entries.

    Returns warnings for any broken evidence links. Filters invalid IDs in-place
    to maintain data integrity at each pipeline node.
    """
    valid_ids: set[str] = {d.doc_id for d in docs}
    warnings: list[str] = []

    if sentiments is not None:
        orphan_sentiment = sum(1 for s in sentiments if s.doc_id not in valid_ids)
        if orphan_sentiment:
            warnings.append(f"情感分析: {orphan_sentiment} 条结果的 doc_id 无法回溯到证据文档")

    if opinions is not None:
        for camp_name, camp_items in [
            ("支持观点", opinions.supports),
            ("反对观点", opinions.opposes),
            ("中立观点", opinions.neutrals),
            ("争议焦点", opinions.controversy_points),
        ]:
            for op in camp_items:
                before = len(op.evidence_ids)
                op.evidence_ids = [eid for eid in op.evidence_ids if eid in valid_ids]
                removed = before - len(op.evidence_ids)
                if removed:
                    warnings.append(f"观点({camp_name}): {removed} 个证据ID无法回溯，已移除")

    if risk is not None:
        before = len(risk.evidence_ids)
        risk.evidence_ids = [eid for eid in risk.evidence_ids if eid in valid_ids]
        removed = before - len(risk.evidence_ids)
        if removed:
            warnings.append(f"风险研判: {removed} 个证据ID无法回溯，已移除")

    if forecast is not None:
        before = len(forecast.evidence_ids)
        forecast.evidence_ids = [eid for eid in forecast.evidence_ids if eid in valid_ids]
        removed = before - len(forecast.evidence_ids)
        if removed:
            warnings.append(f"趋势预测: {removed} 个证据ID无法回溯，已移除")

    return warnings


class TopicAnalysisPipeline:
    """舆情分析主流水线，按 8 个步骤顺序执行：

    1. collect — 数据采集（DB + 外部检索 + MindSpider）
    2. preprocess — 去重清洗
    3. sentiment — 情感分析
    4. opinion — 观点阵营抽取
    5. risk — 风险研判
    6. forecast — 趋势预测
    7. evidence_chain — 证据链校验
    8. report — 报告生成
    """

    def __init__(self) -> None:
        self.llm = LLMGateway()
        self.preprocess_agent = PreprocessAgent()
        self.sentiment_agent = SentimentAgent(self.llm)
        self.opinion_agent = OpinionAgent(self.llm)
        self.risk_agent = RiskAgent(self.llm)
        self.forecast_agent = ForecastAgent(self.llm)
        self.report_agent = ReportAgent(self.llm)

        self.bocha = ExternalBocha()
        self.tavily = ExternalTavily()
        self.mindspider = MindSpiderAdapter()
        self.fusion = DataFusionService()

    # ── Helper: log collector with elapsed-time display ────────────
    @staticmethod
    def _make_log_collector(
        label: str,
        step_start: float,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[list[dict[str, Any]], Callable[[dict[str, Any]], None]]:
        bucket: list[dict[str, Any]] = []
        def _cb(entry: dict[str, Any]) -> None:
            elapsed = time.time() - step_start
            bucket.append(entry)
            if progress_callback:
                progress_callback(f"{label} ({elapsed:.1f}s): {entry['msg']}")
        return bucket, _cb

    # ── Step methods ───────────────────────────────────────────────

    def _step_collect(
        self,
        topic_id: str,
        target_date: date | None,
        use_external: bool,
        use_mindspider: bool,
        mindspider_platforms: list[str],
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        warnings: list[str],
        progress_callback: Callable[[str], None] | None,
    ) -> tuple[list[UnifiedDoc], str, list[str]]:
        """Returns (docs, analysis_topic_id, mindspider_kws)."""
        t0 = time.time()
        bucket, cb = self._make_log_collector("采集", t0, progress_callback)
        cb({"ts": "", "msg": "开始数据采集"})

        analysis_topic_id = topic_id  # display name, kept as user input for weak matches
        mindspider_kws: list[str] = [topic_id]
        docs: list[UnifiedDoc] = []

        with session_scope() as session:
            repo = PgRepository(session)
            resolved = repo.resolve_topic_key(topic_id, target_date)
            if not resolved:
                if not use_external:
                                raise ValueError(f"未找到与输入关键词匹配的话题: {topic_id}")
                warnings.append(f"auto_matched: 输入[{topic_id}]未命中数据库话题，切换为外部检索直连模式")
                cb({"ts": "", "msg": "未命中数据库话题，切换外部检索"})
            else:
                db_topic_key = resolved.resolved_key
                if resolved.matched_by in ("exact", "exact_any_date", "partial"):
                    analysis_topic_id = resolved.resolved_key
                if resolved.matched_by == "keyword":
                    fallback_kws = [topic_id] + repo.get_topic_keywords(db_topic_key)
                    mindspider_kws = [topic_id] + repo.get_topic_keywords(db_topic_key)[:2]
                else:
                    fallback_kws = [topic_id]
                docs = repo.load_topic_evidence(db_topic_key, target_date, fallback_keywords=fallback_kws)
                cb({"ts": "", "msg": f"数据库加载 {len(docs)} 条"})

                if analysis_topic_id != topic_id:
                    warnings.append(
                        f"auto_matched: 输入[{topic_id}] -> 匹配[{analysis_topic_id}] (score={resolved.score:.2f})"
                    )

        if use_external:
            if use_mindspider:
                try:
                    cb({"ts": "", "msg": f"MindSpider 爬取中 ({', '.join(mindspider_platforms)})…"})
                    mindspider_docs = self.mindspider.search(
                        keywords=mindspider_kws[:3],
                        platforms=mindspider_platforms,
                    )
                    docs.extend(mindspider_docs)
                    # Sync crawled docs to platform_content with topic tags
                    if mindspider_docs:
                        with session_scope() as session:
                            repo2 = PgRepository(session)
                            inserted = repo2.insert_platform_content(
                                mindspider_docs,
                                topic_id=analysis_topic_id,
                                topic_name=topic_id,
                                keywords=mindspider_kws[:3],
                            )
                            cb({"ts": "", "msg": f"同步入库 {inserted}/{len(mindspider_docs)} 条"})
                except Exception as exc:
                    warnings.append(f"mindspider_failed:{exc}")
                    cb({"ts": "", "msg": f"MindSpider 失败: {exc}"})
            try:
                if settings.bocha_enabled:
                    cb({"ts": "", "msg": "博查检索中…"})
                    docs.extend(self.bocha.search(analysis_topic_id, query=topic_id, limit=EXTERNAL_SEARCH_LIMIT))
            except Exception as exc:
                warnings.append(f"bocha_failed:{exc}")
            try:
                if settings.tavily_enabled:
                    cb({"ts": "", "msg": "Tavily 检索中…"})
                    docs.extend(self.tavily.search(analysis_topic_id, query=topic_id, limit=EXTERNAL_SEARCH_LIMIT))
            except Exception as exc:
                warnings.append(f"tavily_failed:{exc}")

        if not docs:
                raise ValueError(f"未找到可用于分析的证据数据: {topic_id}")

        cb({"ts": "", "msg": f"采集完成，共 {len(docs)} 条"})
        step_no[0] += 1
        agent_logs.append(AgentStepLog(
            step=step_no[0],
            module="collect",
            status="ok",
            input_docs=0,
            output_summary=f"采集文档 {len(docs)} 条",
            evidence_count=len(docs),
            duration_ms=int((time.time() - t0) * 1000),
            logs=bucket,
        ))
        return docs, analysis_topic_id, mindspider_kws

    def _step_preprocess(
        self,
        docs: list[UnifiedDoc],
        analysis_topic_id: str,
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        progress_callback: Callable[[str], None] | None,
    ) -> list[UnifiedDoc]:
        t0 = time.time()
        input_count = len(docs)
        bucket, cb = self._make_log_collector("预处理", t0, progress_callback)
        cb({"ts": "", "msg": "话题相关性过滤+去重清洗中…"})
        docs = self.fusion.merge_and_dedup(docs)
        docs = self.preprocess_agent.run(
            docs, log_callback=cb, topic_id=analysis_topic_id, llm=self.llm,
        )
        step_no[0] += 1
        agent_logs.append(AgentStepLog(
            step=step_no[0],
            module="preprocess",
            status="ok",
            input_docs=input_count,
            output_summary=f"清洗后保留 {len(docs)} 条",
            evidence_count=len(docs),
            duration_ms=int((time.time() - t0) * 1000),
            logs=bucket,
        ))
        return docs

    def _step_sentiment(
        self,
        docs: list[UnifiedDoc],
        analysis_topic_id: str,
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        progress_callback: Callable[[str], None] | None,
    ) -> list[SentimentItem]:
        t0 = time.time()
        bucket, cb = self._make_log_collector("情感分析", t0, progress_callback)
        sentiments = self.sentiment_agent.run(docs, topic_id=analysis_topic_id, log_callback=cb)
        pos = sum(1 for s in sentiments if s.label == "positive")
        neu = sum(1 for s in sentiments if s.label == "neutral")
        neg = sum(1 for s in sentiments if s.label == "negative")
        step_no[0] += 1
        agent_logs.append(AgentStepLog(
            step=step_no[0],
            module="sentiment",
            status="ok",
            input_docs=len(docs),
            output_summary=f"正向{pos}，中性{neu}，负向{neg}",
            evidence_count=len(sentiments),
            duration_ms=int((time.time() - t0) * 1000),
            logs=bucket,
        ))
        return sentiments

    def _step_opinion(
        self,
        analysis_topic_id: str,
        docs: list[UnifiedDoc],
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        progress_callback: Callable[[str], None] | None,
    ) -> OpinionSummary:
        t0 = time.time()
        bucket, cb = self._make_log_collector("观点抽取", t0, progress_callback)
        opinions = self.opinion_agent.run(analysis_topic_id, docs, log_callback=cb)
        total_op_evidence = sum(
            len(op.evidence_ids)
            for camp in [opinions.supports, opinions.opposes, opinions.neutrals, opinions.controversy_points]
            for op in camp
        )
        step_no[0] += 1
        agent_logs.append(AgentStepLog(
            step=step_no[0],
            module="opinion",
            status="ok",
            input_docs=len(docs),
            output_summary=(
                f"支持{len(opinions.supports)}，反对{len(opinions.opposes)}，"
                f"中立{len(opinions.neutrals)}，争议{len(opinions.controversy_points)}"
            ),
            evidence_count=total_op_evidence,
            duration_ms=int((time.time() - t0) * 1000),
            logs=bucket,
        ))
        return opinions

    def _step_risk(
        self,
        docs: list[UnifiedDoc],
        opinions: OpinionSummary,
        analysis_topic_id: str,
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        progress_callback: Callable[[str], None] | None,
    ) -> RiskResult:
        t0 = time.time()
        bucket, cb = self._make_log_collector("风险研判", t0, progress_callback)
        risk = self.risk_agent.run(docs, opinions, topic_id=analysis_topic_id, log_callback=cb)
        risk_label_cn = RISK_LEVEL_MAP.get(risk.risk_level, risk.risk_level)
        step_no[0] += 1
        agent_logs.append(AgentStepLog(
            step=step_no[0],
            module="risk",
            status="ok",
            input_docs=len(docs),
            output_summary=f"风险等级：{risk_label_cn}",
            evidence_count=len(risk.evidence_ids),
            duration_ms=int((time.time() - t0) * 1000),
            logs=bucket,
        ))
        return risk

    def _step_forecast(
        self,
        docs: list[UnifiedDoc],
        enable_forecast: bool,
        analysis_topic_id: str,
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        progress_callback: Callable[[str], None] | None,
    ) -> ForecastResult | None:
        if enable_forecast:
            t0 = time.time()
            bucket, cb = self._make_log_collector("趋势预测", t0, progress_callback)
            forecast = self.forecast_agent.run(docs, topic_id=analysis_topic_id, log_callback=cb)
            trend_cn = TREND_MAP.get(forecast.trend_judgement, forecast.trend_judgement)
            step_no[0] += 1
            agent_logs.append(AgentStepLog(
                step=step_no[0],
                module="forecast",
                status="ok",
                input_docs=len(docs),
                output_summary=f"趋势{trend_cn}",
                evidence_count=len(forecast.evidence_ids),
                duration_ms=int((time.time() - t0) * 1000),
                logs=bucket,
            ))
            return forecast
        else:
            step_no[0] += 1
            agent_logs.append(AgentStepLog(
                step=step_no[0],
                module="forecast",
                status="skipped",
                input_docs=len(docs),
                output_summary="未启用",
                evidence_count=0,
                duration_ms=0,
            ))
            return None

    def _step_evidence_chain(
        self,
        docs: list[UnifiedDoc],
        sentiments: list[SentimentItem],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        enable_forecast: bool,
        warnings: list[str],
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        progress_callback: Callable[[str], None] | None,
    ) -> None:
        t0 = time.time()
        chain_bucket: list[dict[str, Any]] = []
        if progress_callback:
            progress_callback(f"证据链校验 (0.0s): 检查中…")
        evidence_warnings = _verify_evidence_chain(
            docs=docs,
            sentiments=sentiments,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
        )
        warnings.extend(evidence_warnings)
        nodes_checked = 4 if enable_forecast else 3
        chain_bucket.append({
            "ts": "",
            "msg": "全部校验通过" if not evidence_warnings else f"发现 {len(evidence_warnings)} 个断链",
        })
        step_no[0] += 1
        agent_logs.append(AgentStepLog(
            step=step_no[0],
            module="evidence_chain",
            status="ok",
            input_docs=len(docs),
            output_summary=(
                "全部校验通过" if not evidence_warnings
                else f"发现 {len(evidence_warnings)} 个断链"
            ),
            evidence_count=nodes_checked,
            duration_ms=int((time.time() - t0) * 1000),
            logs=chain_bucket,
        ))

    def _step_report(
        self,
        analysis_topic_id: str,
        docs: list[UnifiedDoc],
        sentiments: list[SentimentItem],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        step_no: list[int],
        agent_logs: list[AgentStepLog],
        progress_callback: Callable[[str], None] | None,
    ) -> TopicReport:
        t0 = time.time()
        bucket, cb = self._make_log_collector("报告生成", t0, progress_callback)
        report = self.report_agent.run(
            topic_id=analysis_topic_id,
            docs=docs,
            source_distribution=self.fusion.source_distribution(docs),
            sentiments=sentiments,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
            log_callback=cb,
        )
        step_no[0] += 1
        agent_logs.append(AgentStepLog(
            step=step_no[0],
            module="report",
            status="ok",
            input_docs=len(docs),
            output_summary="报告已生成",
            evidence_count=len(report.evidence_list),
            duration_ms=int((time.time() - t0) * 1000),
            logs=bucket,
        ))
        return report

    # ── Main orchestration ─────────────────────────────────────────

    def run(
        self,
        topic_id: str,
        target_date: date | None,
        enable_forecast: bool,
        use_external: bool,
        use_mindspider: bool = False,
        mindspider_platforms: list[str] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[TopicReport, list[str], str, list[AgentStepLog]]:
        # Date filtering is intentionally disabled: always search across all time ranges.
        target_date = None
        warnings: list[str] = []
        agent_logs: list[AgentStepLog] = []
        step_no = [0]  # mutable int via single-element list

        # Step 1: collect
        if mindspider_platforms is None:
            mindspider_platforms = ["xhs"]
        docs, analysis_topic_id, mindspider_kws = self._step_collect(
            topic_id=topic_id,
            target_date=target_date,
            use_external=use_external,
            use_mindspider=use_mindspider,
            mindspider_platforms=mindspider_platforms,
            step_no=step_no,
            agent_logs=agent_logs,
            warnings=warnings,
            progress_callback=progress_callback,
        )

        # Step 2: preprocess
        docs = self._step_preprocess(
            docs=docs,
            analysis_topic_id=analysis_topic_id,
            step_no=step_no,
            agent_logs=agent_logs,
            progress_callback=progress_callback,
        )

        # Step 3: sentiment
        sentiments = self._step_sentiment(
            docs=docs,
            analysis_topic_id=analysis_topic_id,
            step_no=step_no,
            agent_logs=agent_logs,
            progress_callback=progress_callback,
        )

        # Step 4: opinion
        opinions = self._step_opinion(
            analysis_topic_id=analysis_topic_id,
            docs=docs,
            step_no=step_no,
            agent_logs=agent_logs,
            progress_callback=progress_callback,
        )

        # Step 5: risk
        risk = self._step_risk(
            docs=docs,
            opinions=opinions,
            analysis_topic_id=analysis_topic_id,
            step_no=step_no,
            agent_logs=agent_logs,
            progress_callback=progress_callback,
        )

        # Step 6: forecast
        forecast = self._step_forecast(
            docs=docs,
            enable_forecast=enable_forecast,
            analysis_topic_id=analysis_topic_id,
            step_no=step_no,
            agent_logs=agent_logs,
            progress_callback=progress_callback,
        )

        # Step 7: evidence chain verification
        self._step_evidence_chain(
            docs=docs,
            sentiments=sentiments,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
            enable_forecast=enable_forecast,
            warnings=warnings,
            step_no=step_no,
            agent_logs=agent_logs,
            progress_callback=progress_callback,
        )

        # Step 8: report
        report = self._step_report(
            analysis_topic_id=analysis_topic_id,
            docs=docs,
            sentiments=sentiments,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
            step_no=step_no,
            agent_logs=agent_logs,
            progress_callback=progress_callback,
        )

        return report, warnings, self.mindspider.last_log, agent_logs
