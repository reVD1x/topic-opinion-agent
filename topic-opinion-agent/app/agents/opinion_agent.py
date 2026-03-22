from __future__ import annotations

from app.llm.gateway import LLMGateway
from app.schemas.analysis import OpinionSummary
from app.schemas.doc import UnifiedDoc


class OpinionAgent:
    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(self, topic_id: str, docs: list[UnifiedDoc]) -> OpinionSummary:
        if not docs:
            return OpinionSummary(supports=[], opposes=[], neutrals=[], controversy_points=[])

        if not self.llm.enabled:
            return OpinionSummary(
                supports=["样本中存在支持性表达"],
                opposes=["样本中存在质疑性表达"],
                neutrals=["样本中存在事实转述"],
                controversy_points=["核心争议尚不明确，需补充语料"],
            )

        joined = "\n".join([f"- {d.content[:220]}" for d in docs[:40]])
        rsp = self.llm.chat_json(
            system_prompt=(
                "Extract opinion camps for one topic. "
                "Output JSON {supports:[], opposes:[], neutrals:[], controversy_points:[]}."
            ),
            user_prompt=f"topic_id={topic_id}\ncontent:\n{joined}",
        )

        try:
            return OpinionSummary(**rsp)
        except Exception:
            return OpinionSummary(supports=[], opposes=[], neutrals=[], controversy_points=[])
