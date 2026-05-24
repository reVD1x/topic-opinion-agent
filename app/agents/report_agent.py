"""报告生成 Agent — 汇总各模块输出为结构化 TopicReport 和 Markdown 报告。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.common.constants import (
    EVIDENCE_MAX_ITEMS,
    MODULE_NAME_MAP,
    RISK_LEVEL_MAP,
    TIME_HORIZON_MAP,
    TREND_MAP,
    UNCERTAINTY_MAP,
    to_cn,
)
from app.common.utils import ts
from app.llm.gateway import LLMGateway
from app.schemas.analysis import ForecastResult, OpinionSummary, RiskResult, SentimentItem
from app.schemas.doc import UnifiedDoc
from app.schemas.report import EvidenceItem, TopicReport

logger = logging.getLogger(__name__)


class ReportAgent:
    """接收 pipeline 各步骤输出，生成模块总结、综合总结和 Markdown 报告。

    通常作为 pipeline 最后一步调用。
    """

    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(
        self,
        topic_id: str,
        docs: list[UnifiedDoc],
        source_distribution: dict[str, int],
        sentiments: list[SentimentItem],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> TopicReport:
        if log_callback:
            log_callback({"ts": ts(), "msg": "开始生成报告"})

        summary = {"positive": 0, "neutral": 0, "negative": 0}
        for s in sentiments:
            summary[s.label] += 1

        evidence = [
            EvidenceItem(doc_id=d.doc_id, source_type=d.source_type, title=d.title, url=d.url)
            for d in docs[:EVIDENCE_MAX_ITEMS]
        ]

        if log_callback:
            log_callback({"ts": ts(), "msg": f"生成模块总结（7 个模块）…"})

        module_summaries = self._build_module_summaries(
            docs=docs,
            source_distribution=source_distribution,
            sentiment_summary=summary,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
            evidence_count=len(evidence),
            log_callback=log_callback,
        )

        if log_callback:
            log_callback({"ts": ts(), "msg": "生成综合总结…"})

        narrative = self._build_narrative_summary(
            topic_id=topic_id,
            source_distribution=source_distribution,
            sentiment_summary=summary,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
            log_callback=log_callback,
        )

        if log_callback:
            log_callback({"ts": ts(), "msg": "生成 Markdown 报告"})

        md = self._build_markdown(topic_id, source_distribution, summary, opinions, risk, forecast, module_summaries, narrative)

        if log_callback:
            log_callback({"ts": ts(), "msg": f"报告完成：{len(evidence)} 条证据，{len(summary)} 类情感"})

        logger.info("报告完成：%d 条证据，%d 类情感", len(evidence), len(summary))
        return TopicReport(
            topic_id=topic_id,
            overview=f"样本总量 {len(docs)}，覆盖 {len(source_distribution)} 类来源。",
            source_distribution=source_distribution,
            sentiment_summary=summary,
            sentiment_items=sentiments,
            opinion_blocks=opinions,
            risk=risk,
            evidence_list=evidence,
            forecast=forecast,
            module_summaries=module_summaries,
            narrative_summary=narrative,
            markdown=md,
        )

    def _build_module_summaries(
        self,
        docs: list[UnifiedDoc],
        source_distribution: dict[str, int],
        sentiment_summary: dict[str, int],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        evidence_count: int,
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, str]:
        top_source = "unknown"
        if source_distribution:
            top_source = max(source_distribution.items(), key=lambda item: item[1])[0]

        summaries: dict[str, str] = {}
        module_contexts: dict[str, dict[str, Any]] = {
            "collect": {
                "doc_count": len(docs),
                "source_types": len(source_distribution),
                "top_source": top_source,
            },
            "preprocess": {
                "doc_count_after_clean": len(docs),
                "has_content": any(bool(d.content) for d in docs),
            },
            "sentiment": sentiment_summary,
            "opinion": {
                "supports": len(opinions.supports),
                "opposes": len(opinions.opposes),
                "neutrals": len(opinions.neutrals),
                "controversy_points": len(opinions.controversy_points),
            },
            "risk": {
                "risk_level": risk.risk_level,
                "trigger_count": len(risk.triggers),
                "evidence_count": len(risk.evidence_ids),
                "time_sensitivity": risk.time_sensitivity,
                "time_rationale": risk.time_rationale,
            },
            "forecast": (
                {
                    "enabled": True,
                    "trend": forecast.trend_judgement,
                    "horizon": forecast.time_horizon,
                    "uncertainty": forecast.uncertainty,
                }
                if forecast
                else {"enabled": False}
            ),
            "report": {
                "evidence_items": evidence_count,
                "contains_forecast": forecast is not None,
            },
        }

        for module_name, context in module_contexts.items():
            summaries[module_name] = self._summarize_module(module_name, context, log_callback=log_callback)

        return summaries

    def _summarize_module(
        self,
        module_name: str,
        context: dict[str, Any],
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> str:
        """对单个模块调用 LLM 生成一句话总结。LLM 不可用时返回格式化回退文本。"""
        if not self.llm.enabled:
            return f"{module_name}模块已完成，关键信息：{context}"

        rsp = self.llm.chat_json(
            system_prompt=(
                "你是舆情分析流水线助手。请按以下步骤思考：\n"
                "1. 理解模块数据中的关键指标与数值含义。\n"
                "2. 提炼该模块最核心的1-2个发现。\n"
                "3. 用精炼中文总结，控制在60字内。\n"
                "输出JSON: {summary:string}。"
            ),
            user_prompt=f"module={module_name}\ncontext={context}",
        )
        summary = rsp.get("summary") if isinstance(rsp, dict) else None
        if isinstance(summary, str) and summary.strip():
            if log_callback:
                log_callback({"ts": ts(), "msg": f"  {module_name} 模块总结完成"})
            return summary.strip()
        return f"{module_name}模块已完成，关键信息：{context}"

    def _build_narrative_summary(
        self,
        topic_id: str,
        source_distribution: dict[str, int],
        sentiment_summary: dict[str, int],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> str:
        """生成 350-500 字中文综合总结，涵盖话题扫描、情感诊断、观点梳理、风险评估、趋势预判五个维度。"""
        total = sum(sentiment_summary.values())
        positive = sentiment_summary.get("positive", 0)
        negative = sentiment_summary.get("negative", 0)
        neutral = sentiment_summary.get("neutral", 0)

        if total > 0:
            positive_pct = positive / total * 100
            negative_pct = negative / total * 100
            if positive_pct > negative_pct:
                sentiment_trend = "整体偏正面"
            elif negative_pct > positive_pct:
                sentiment_trend = "整体偏负面"
            else:
                sentiment_trend = "正负均衡"
        else:
            sentiment_trend = "暂无足够数据判断情感倾向"

        risk_label = to_cn(RISK_LEVEL_MAP, risk.risk_level)
        trigger_list = "、".join(risk.triggers[:5]) if risk.triggers else "未发现明显触发词"
        time_sensitivity_map = {"immediate": "即刻（数小时至数天）", "short_term": "短期（数周至数月）", "long_term": "长期（持续性背景风险）"}
        time_label = time_sensitivity_map.get(risk.time_sensitivity, "短期")
        sources = "、".join(f"{k}({v})" for k, v in sorted(source_distribution.items(), key=lambda x: x[1], reverse=True)[:5])

        context = {
            "topic": topic_id,
            "total_samples": total,
            "source_distribution": sources,
            "sentiment": f"正向{positive}，中性{neutral}，负向{negative}，{sentiment_trend}",
            "supports": [op.content for op in opinions.supports[:5]] if opinions.supports else ["无"],
            "opposes": [op.content for op in opinions.opposes[:5]] if opinions.opposes else ["无"],
            "controversy": [op.content for op in opinions.controversy_points[:5]] if opinions.controversy_points else ["无"],
            "risk_level": risk_label,
            "risk_triggers": trigger_list,
            "risk_time_sensitivity": time_label,
            "risk_time_rationale": risk.time_rationale,
            "forecast": (
                f"趋势{to_cn(TREND_MAP, forecast.trend_judgement)}，不确定性{to_cn(UNCERTAINTY_MAP, forecast.uncertainty)}"
                if forecast
                else "未启用"
            ),
        }

        if not self.llm.enabled:
            return self._fallback_narrative(context)

        rsp = self.llm.chat_json(
            system_prompt=(
                "你是资深舆情分析师。请按以下步骤进行分析与撰写：\n\n"
                "1. 话题扫描 — 审视话题概况、样本总量与来源分布，判断舆论场规模与多样性。\n"
                "2. 情感诊断 — 分析正/中/负情感比例，判断整体舆论基调及其可能原因。\n"
                "3. 观点梳理 — 提炼支持方与反对方的核心论点，识别争议焦点与共识区域。\n"
                "4. 风险评估 — 结合触发因素、观点对立程度与时间紧迫性，评估当前风险等级的现实含义。"
                "重点着眼于短期（数日至数周内）可能爆发的舆情事件，区分即刻威胁与长期背景噪音。\n"
                "5. 趋势预判 — 基于现有信号与不确定性，做出短期走向判断。\n\n"
                "完成分析后，撰写一段350-500字的中文综合总结，涵盖以上五个维度。"
                "语言精炼专业，直接给出总结段落，不需要标题或分点。"
                "输出JSON: {narrative:string}。"
            ),
            user_prompt=f"analysis_context:\n{context}",
        )
        narrative = rsp.get("narrative") if isinstance(rsp, dict) else None
        if isinstance(narrative, str) and narrative.strip():
            return narrative.strip()
        return self._fallback_narrative(context)

    @staticmethod
    def _fallback_narrative(context: dict[str, Any]) -> str:
        """LLM 不可用时的模板化总结回退。"""
        return (
            f"针对话题「{context['topic']}」的分析显示，共采集样本{context['total_samples']}条，"
            f"来源覆盖{context['source_distribution']}。"
            f"情感分布为{context['sentiment']}。"
            f"风险等级评定为{context['risk_level']}（时间敏感性：{context.get('risk_time_sensitivity', '短期')}），"
            f"触发因素包括{context['risk_triggers']}。"
            f"趋势预测：{context['forecast']}。"
        )

    @staticmethod
    def _build_markdown(
        topic_id: str,
        source_distribution: dict[str, int],
        sentiment_summary: dict[str, int],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        module_summaries: dict[str, str],
        narrative_summary: str = "",
    ) -> str:
        """构建完整的 Markdown 格式分析报告。"""
        lines = [f"# 话题分析报告：{topic_id}", ""]

        if narrative_summary:
            lines.extend(["## 综合总结", "", narrative_summary, ""])

        lines.extend(["## 来源分布"])

        if source_distribution:
            lines.extend(["| 来源类型 | 数量 |", "| --- | ---: |"])
            for source, count in sorted(source_distribution.items(), key=lambda item: item[1], reverse=True):
                lines.append(f"| {source} | {count} |")
        else:
            lines.append("- 无来源数据")

        lines.extend(["", "## 情感统计", "| 情感倾向 | 数量 |", "| --- | ---: |"])
        lines.append(f"| 正向 | {sentiment_summary.get('positive', 0)} |")
        lines.append(f"| 中性 | {sentiment_summary.get('neutral', 0)} |")
        lines.append(f"| 负向 | {sentiment_summary.get('negative', 0)} |")

        def _fmt_opinion(items) -> list[str]:
            if not items:
                return ["- 无"]
            out: list[str] = []
            for op in items:
                ids = ", ".join(op.evidence_ids[:3])
                out.append(f"- {op.content}  `[{ids}]`")
            return out

        lines.extend(["", "## 观点阵营", "### 支持观点"])
        lines.extend(_fmt_opinion(opinions.supports))
        lines.extend(["", "### 反对观点"])
        lines.extend(_fmt_opinion(opinions.opposes))
        lines.extend(["", "### 中立观点"])
        lines.extend(_fmt_opinion(opinions.neutrals))
        lines.extend(["", "### 争议焦点"])
        lines.extend(_fmt_opinion(opinions.controversy_points))

        lines.extend(["", "## 风险研判", f"- 风险等级：{to_cn(RISK_LEVEL_MAP, risk.risk_level)}", "- 触发因素："])
        lines.extend([f"  - {item}" for item in risk.triggers] or ["  - 无"])

        lines.append("- 证据 ID（最多 10 条）：")
        lines.extend([f"  - `{doc_id}`" for doc_id in risk.evidence_ids[:10]] or ["  - 无"])

        lines.extend(["", "## 模块总结"])
        for module_name, summary in module_summaries.items():
            lines.append(f"- {to_cn(MODULE_NAME_MAP, module_name)}：{summary}")

        if forecast:
            lines.extend(
                [
                    "",
                    "## 趋势预测（仅基于 LLM 推断）",
                    f"- 趋势判断：{to_cn(TREND_MAP, forecast.trend_judgement)}",
                    f"- 时间窗：{to_cn(TIME_HORIZON_MAP, forecast.time_horizon)}",
                    f"- 不确定性：{to_cn(UNCERTAINTY_MAP, forecast.uncertainty)}",
                    "- 关键假设：",
                ]
            )
            lines.extend([f"  - {item}" for item in forecast.assumptions] or ["  - 无"])

            lines.append("- 反事实：")
            lines.extend([f"  - {item}" for item in forecast.counterfactuals] or ["  - 无"])

            lines.append("- 关键证据 ID：")
            if forecast.evidence_ids:
                lines.extend([f"  - `{doc_id}`" for doc_id in forecast.evidence_ids[:10]])
            else:
                lines.append("  - 无")

            lines.append(f"\n  - 说明：{forecast.disclaimer}")

        return "\n".join(lines)
