from __future__ import annotations

from app.llm.gateway import LLMGateway
from app.schemas.analysis import SentimentItem
from app.schemas.doc import UnifiedDoc


class SentimentAgent:
    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(self, docs: list[UnifiedDoc]) -> list[SentimentItem]:
        if not docs:
            return []

        if not self.llm.enabled:
            # Fallback heuristic for local execution without LLM credentials.
            return [
                SentimentItem(doc_id=d.doc_id, label="neutral", confidence=0.5)
                for d in docs
            ]

        prompt = "\n".join([f"{d.doc_id}: {d.content[:300]}" for d in docs[:30]])
        rsp = self.llm.chat_json(
            system_prompt=(
                "Classify sentiment for each line. Output JSON: "
                "{items:[{doc_id,label,confidence}]}. label in positive/neutral/negative."
            ),
            user_prompt=prompt,
        )
        items = rsp.get("items", []) if isinstance(rsp, dict) else []
        parsed: list[SentimentItem] = []
        for item in items:
            try:
                parsed.append(SentimentItem(**item))
            except Exception:
                continue
        if not parsed:
            parsed = [SentimentItem(doc_id=d.doc_id, label="neutral", confidence=0.5) for d in docs]
        return parsed
