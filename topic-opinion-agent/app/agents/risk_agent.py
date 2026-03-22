from __future__ import annotations

from app.llm.gateway import LLMGateway
from app.schemas.analysis import OpinionSummary, RiskResult
from app.schemas.doc import UnifiedDoc


class RiskAgent:
    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(self, docs: list[UnifiedDoc], opinion: OpinionSummary) -> RiskResult:
        if not docs:
            return RiskResult(risk_level="low", triggers=["empty_sample"], evidence_ids=[])

        trigger_words = ["谣言", "冲突", "抵制", "维权", "事故", "违法", "伤亡"]
        hits: list[str] = []
        evidence_ids: list[str] = []
        for doc in docs:
            for word in trigger_words:
                if word in doc.content:
                    hits.append(word)
                    evidence_ids.append(doc.doc_id)
                    break

        if len(hits) >= 8:
            level = "high"
        elif len(hits) >= 3:
            level = "medium"
        else:
            level = "low"

        if self.llm.enabled and docs:
            # LLM is used only for trigger refinement, not replacing deterministic baseline.
            rsp = self.llm.chat_json(
                system_prompt=(
                    "Given baseline triggers and key opinions, output JSON "
                    "{extra_triggers:[string]}."
                ),
                user_prompt=(
                    f"baseline={hits[:8]}\n"
                    f"opinion={opinion.model_dump()}\n"
                    f"sample={[d.content[:120] for d in docs[:8]]}"
                ),
            )
            extra = rsp.get("extra_triggers", []) if isinstance(rsp, dict) else []
            if isinstance(extra, list):
                hits.extend([str(i) for i in extra[:5]])

        return RiskResult(
            risk_level=level,
            triggers=list(dict.fromkeys(hits))[:10],
            evidence_ids=list(dict.fromkeys(evidence_ids))[:20],
        )
