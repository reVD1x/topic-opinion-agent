"""趋势预测 Agent — 基于 LLM 的舆情趋势推断（上升/平稳/下降）。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.common.constants import FORECAST_MAX_DOCS, FORECAST_SNIPPET_LEN
from app.common.utils import ts
from app.llm.gateway import LLMGateway
from app.schemas.analysis import ForecastResult
from app.schemas.doc import UnifiedDoc

logger = logging.getLogger(__name__)


class ForecastAgent:
    """对文档集合进行趋势预测（rise/flat/fall）、时间窗判断和不确定性评估。

    LLM 不可用时返回保守默认值（flat / high uncertainty）。
    """

    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(
        self,
        docs: list[UnifiedDoc],
        topic_id: str = "",
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> ForecastResult:
        """执行趋势预测。

        Args:
            docs: 待分析的文档列表。
            topic_id: 目标话题名称，用于将预测与话题紧密关联。
            log_callback: 可选进度回调。

        Returns:
            包含趋势判断、假设、反事实等字段的 ForecastResult。
        """
        if not docs or not self.llm.enabled:
            logger.info("LLM 未启用或无文档，使用默认预测")
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 未启用或无文档，使用默认预测"})
            return ForecastResult(
                trend_judgement="flat",
                time_horizon="24h",
                assumptions=["无新增重大事件"],
                counterfactuals=["出现权威通报将改变趋势"],
                uncertainty="high",
                disclaimer="基于LLM推断，非统计预测，仅供参考。",
                evidence_ids=[d.doc_id for d in docs],
            )

        logger.info("开始趋势预测，共 %d 条文档", len(docs))
        if log_callback:
            log_callback({"ts": ts(), "msg": f"开始趋势预测，共 {len(docs)} 条文档"})

        target_docs = docs[:FORECAST_MAX_DOCS]
        # Map short integer IDs → real doc_id so the LLM never sees long URL-based IDs.
        id_map: dict[str, str] = {str(i): d.doc_id for i, d in enumerate(target_docs)}

        logger.info("LLM 推断中（%d 条输入）", len(target_docs))
        if log_callback:
            log_callback({"ts": ts(), "msg": f"LLM 推断中（{len(target_docs)} 条输入）…"})

        topic_context = f"话题：{topic_id}\n\n" if topic_id else ""
        rsp = self.llm.chat_json(
            system_prompt=(
                "你是一个中文舆情趋势预测专家。请针对当前话题，按以下步骤分析：\n\n"
                "1. 情感扫描 — 审视每条文档的情感方向和强度。"
                "与该话题相关的整体舆论基调是向正面、负面还是稳定转变？\n"
                "2. 讨论量轨迹 — 关于该话题的讨论热度是加速上升(rise)、保持平稳(flat)还是下降(fall)？\n"
                "3. 触发因素识别 — 是否有围绕该话题的新事件、争议或官方声明可能改变走向？\n"
                "4. 关键假设 — 明确列出你的预测所依赖的条件，每条假设必须与该话题直接相关。\n"
                "5. 反事实 — 针对每个假设，识别什么情况会逆转对该话题的预测。\n"
                "6. 不确定性评估 — 信息完整度如何？是否存在增加不确定性的信息缺口？\n"
                "7. 关键证据 — 选择3-8条对预测影响最大的文档编号。\n\n"
                "每条文档在输入中以 [数字]: 开头。\n\n"
                "输出JSON包含以下键：\n"
                "  trend_judgement: rise|flat|fall\n"
                "  time_horizon: 24h|72h\n"
                "  assumptions: [string] - 预测的关键假设，用中文\n"
                "  counterfactuals: [string] - 可能逆转预测的情况，用中文\n"
                "  uncertainty: low|medium|high\n"
                "  disclaimer: string - 用中文\n"
                "  reasoning: string - 用中文解释你的分析过程\n"
                '  key_evidence_ids: [string] - 3到8个文档编号（如 "0", "1" 这样的字符串）\n'
            ),
            user_prompt=topic_context + "\n".join(
                [f"[{i}]: {d.content[:FORECAST_SNIPPET_LEN]}" for i, d in enumerate(target_docs)]
            ),
        )

        if not isinstance(rsp, dict):
            logger.warning("LLM 返回格式异常，使用默认预测")
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 返回格式异常，使用默认预测"})
            return ForecastResult(
                trend_judgement="flat",
                time_horizon="24h",
                assumptions=["上下文不足"],
                counterfactuals=["新增信息可能反转"],
                uncertainty="high",
                disclaimer="基于LLM推断，非统计预测，仅供参考。",
                evidence_ids=[d.doc_id for d in docs],
            )

        raw_ids = rsp.get("key_evidence_ids", [])
        if not isinstance(raw_ids, list):
            raw_ids = []
        evidence_ids = [id_map[str(eid)] for eid in raw_ids if str(eid) in id_map]
        if not evidence_ids:
            evidence_ids = [d.doc_id for d in docs[:10]]

        try:
            result = ForecastResult(
                trend_judgement=rsp.get("trend_judgement", "flat"),
                time_horizon=rsp.get("time_horizon", "24h"),
                assumptions=rsp.get("assumptions", []) if isinstance(rsp.get("assumptions"), list) else [],
                counterfactuals=rsp.get("counterfactuals", []) if isinstance(rsp.get("counterfactuals"), list) else [],
                uncertainty=rsp.get("uncertainty", "high"),
                disclaimer=rsp.get("disclaimer", "基于LLM推断，非统计预测，仅供参考。"),
                reasoning=str(rsp.get("reasoning", "")).strip(),
                evidence_ids=evidence_ids,
            )
            logger.info(
                "完成：趋势%s，不确定性%s，%d 条关键证据",
                result.trend_judgement, result.uncertainty, len(result.evidence_ids),
            )
            if log_callback:
                trend_cn = {"rise": "上升", "flat": "平稳", "fall": "下降"}.get(result.trend_judgement, result.trend_judgement)
                log_callback({
                    "ts": ts(),
                    "msg": f"完成：趋势{trend_cn}，不确定性{result.uncertainty}，{len(result.evidence_ids)} 条关键证据",
                })
            return result
        except Exception:
            logger.exception("解析异常，使用默认预测")
            if log_callback:
                log_callback({"ts": ts(), "msg": "解析异常，使用默认预测"})
            return ForecastResult(
                trend_judgement="flat",
                time_horizon="24h",
                assumptions=["解析失败"],
                counterfactuals=["新增信息可能反转"],
                uncertainty="high",
                disclaimer="基于LLM推断，非统计预测，仅供参考。",
                evidence_ids=[d.doc_id for d in docs[:10]],
            )
