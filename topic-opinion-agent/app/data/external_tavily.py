from __future__ import annotations

from typing import Any

import requests

from app.common.config import settings
from app.schemas.doc import UnifiedDoc


class ExternalTavily:
    def search(self, topic_id: str, query: str, limit: int = 10) -> list[UnifiedDoc]:
        if not settings.tavily_api_key:
            return []

        payload = {
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": limit,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": True,
        }
        response = requests.post(settings.tavily_base_url, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()

        items = data.get("results", []) if isinstance(data, dict) else []
        return [self._to_doc(topic_id, i) for i in items if i.get("content")]

    @staticmethod
    def _to_doc(topic_id: str, item: dict[str, Any]) -> UnifiedDoc:
        raw_id = str(item.get("url") or item.get("title") or "tavily")
        return UnifiedDoc(
            doc_id=f"tavily:{raw_id}",
            topic_id=topic_id,
            source_type="tavily",
            source_name=item.get("source") or "tavily",
            title=item.get("title"),
            content=item.get("content", ""),
            url=item.get("url"),
            author=None,
            credibility_hint="external",
        )
