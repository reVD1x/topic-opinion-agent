"""风险研判 Agent — 关键词基线扫描 + LLM 补充触发词，输出风险等级。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.common.constants import (
    RISK_HIGH_THRESHOLD,
    RISK_MEDIUM_THRESHOLD,
    RISK_SNIPPET_LEN,
    RISK_SAMPLE_DOCS,
    TRIGGER_WORDS,
)
from app.common.utils import ts
from app.llm.gateway import LLMGateway
from app.schemas.analysis import OpinionSummary, RiskResult
from app.schemas.doc import UnifiedDoc

logger = logging.getLogger(__name__)


class RiskAgent:
    """风险研判：先基于触发词进行确定性基线扫描，再通过 LLM 补充额外风险因素。

    基线扫描结果不依赖 LLM，确保可复现性；LLM 仅用于补充发现。
    研判时加入时间维度，着眼于短期（数日至数周内）可触发舆情事件的风险。
    """

    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(
        self,
        docs: list[UnifiedDoc],
        opinion: OpinionSummary,
        topic_id: str = "",
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> RiskResult:
        """执行风险研判。

        Args:
            docs: 待扫描的文档列表。
            opinion: 前置步骤的观点摘要，用于 LLM 交叉分析。
            topic_id: 目标话题名称，用于将风险分析与话题紧密关联。
            log_callback: 可选进度回调。

        Returns:
            包含风险等级、触发因素列表和证据 ID 的 RiskResult。
        """
        if not docs:
            return RiskResult(risk_level="low", triggers=["empty_sample"], evidence_ids=[])

        logger.info("开始风险研判，扫描 %d 条文档", len(docs))
        if log_callback:
            log_callback({"ts": ts(), "msg": f"开始风险研判，扫描 {len(docs)} 条文档"})

        hits: list[str] = []
        evidence_ids: list[str] = []
        for doc in docs:
            for word in TRIGGER_WORDS:
                if word in doc.content:
                    hits.append(word)
                    evidence_ids.append(doc.doc_id)
                    break

        if len(hits) >= RISK_HIGH_THRESHOLD:
            level = "high"
        elif len(hits) >= RISK_MEDIUM_THRESHOLD:
            level = "medium"
        else:
            level = "low"

        logger.info("基线扫描：命中 %d 个触发词，风险等级 %s", len(hits), level)
        if log_callback:
            log_callback({
                "ts": ts(),
                "msg": f"基线扫描：命中 {len(hits)} 个触发词（{', '.join(hits[:5])}），风险等级 {level}"
            })

        if self.llm.enabled and docs:
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 补充触发词与时间研判中…"})
            topic_context = f"话题：{topic_id}\n\n" if topic_id else ""
            rsp = self.llm.chat_json(
                system_prompt=(
                    "你是一个中文舆情风险分析师。请针对当前话题，审查以下基线触发词和样本文档：\n"
                    "1. 评估每个基线触发词是否代表真正的风险信号还是误报——"
                    "该触发词是否确实指向与该话题相关的风险，而非不相关语境中的偶然出现。\n"
                    "2. 阅读样本文档，发现关键词列表未覆盖的风险指标"
                    "（如声誉威胁、监管风险、公众愤怒、虚假信息模式）。\n"
                    "3. 考虑观点极化和触发词密度的叠加效应——"
                    "多个触发因素同时出现是否会放大该话题的风险？\n"
                    "4. 评估风险的时间紧迫性——区分以下三类：\n"
                    "   · immediate（即刻风险）：数小时至数天内可能爆发舆情事件，需立即关注\n"
                    "   · short_term（短期风险）：数周至数月内可能发展，需保持监测\n"
                    "   · long_term（长期风险）：持续存在的背景性风险，暂无爆发迹象\n"
                    "   着眼于短期与即刻风险。若无明显爆发迹象，即使背景风险存在，也应倾向于评级为短期或长期。\n\n"
                    "完成分析后，输出JSON: {extra_triggers:[string], time_sensitivity:string, time_rationale:string}。\n"
                    "extra_triggers 中每个元素应为中文短语，直接描述风险点。\n"
                    "time_sensitivity 取值为 immediate/short_term/long_term。\n"
                    "time_rationale 为一句话理由。"
                ),
                user_prompt=(
                    topic_context +
                    f"baseline={hits[:8]}\n"
                    f"opinion={opinion.model_dump()}\n"
                    f"sample={[d.content[:RISK_SNIPPET_LEN] for d in docs[:RISK_SAMPLE_DOCS]]}"
                ),
            )
            extra = rsp.get("extra_triggers", []) if isinstance(rsp, dict) else []
            time_sensitivity = rsp.get("time_sensitivity", "short_term") if isinstance(rsp, dict) else "short_term"
            time_rationale = rsp.get("time_rationale", "") if isinstance(rsp, dict) else ""
            if isinstance(extra, list):
                hits.extend([str(i) for i in extra[:5]])
            logger.info("LLM 补充 %d 个触发词，时间敏感性: %s", len(extra), time_sensitivity)
            if log_callback:
                log_callback({"ts": ts(), "msg": f"LLM 补充 {len(extra)} 个触发词，时间敏感性: {time_sensitivity}"})
        else:
            time_sensitivity = "short_term"
            time_rationale = ""

        result = RiskResult(
            risk_level=level,
            triggers=list(dict.fromkeys(hits))[:10],
            evidence_ids=list(dict.fromkeys(evidence_ids))[:20],
            time_sensitivity=time_sensitivity,
            time_rationale=time_rationale,
        )

        logger.info(
            "完成：风险等级 %s，%d 个触发因素，%d 条证据",
            level, len(result.triggers), len(result.evidence_ids),
        )
        if log_callback:
            log_callback({
                "ts": ts(),
                "msg": f"完成：风险等级 {level}，{len(result.triggers)} 个触发因素，{len(result.evidence_ids)} 条证据",
            })

        return result
