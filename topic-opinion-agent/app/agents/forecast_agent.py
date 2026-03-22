from __future__ import annotations

from app.llm.gateway import LLMGateway
from app.schemas.analysis import ForecastResult
from app.schemas.doc import UnifiedDoc


class ForecastAgent:
    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(self, docs: list[UnifiedDoc]) -> ForecastResult:
        if not docs or not self.llm.enabled:
            return ForecastResult(
                trend_judgement="flat",
                time_horizon="24h",
                assumptions=["无新增重大事件"],
                counterfactuals=["出现权威通报将改变趋势"],
                uncertainty="high",
                disclaimer="基于LLM推断，非统计预测，仅供参考。",
            )

        rsp = self.llm.chat_json(
            system_prompt=(
                "Make short-term trend inference only. "
                "Output JSON keys: trend_judgement(rise|flat|fall), time_horizon(24h|72h), "
                "assumptions, counterfactuals, uncertainty(low|medium|high), disclaimer."
            ),
            user_prompt="\n".join([d.content[:220] for d in docs[:20]]),
        )

        try:
            return ForecastResult(**rsp)
        except Exception:
            return ForecastResult(
                trend_judgement="flat",
                time_horizon="24h",
                assumptions=["上下文不足"],
                counterfactuals=["新增信息可能反转"],
                uncertainty="high",
                disclaimer="基于LLM推断，非统计预测，仅供参考。",
            )
