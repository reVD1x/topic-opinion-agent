from __future__ import annotations

from typing import Any

import requests

from app.common.config import settings
from app.schemas.doc import UnifiedDoc


class ExternalBocha:
    def search(self, topic_id: str, query: str, limit: int = 10) -> list[UnifiedDoc]:
        if not settings.bocha_api_key or not settings.bocha_base_url:
            return []

        headers = {"Authorization": f"Bearer {settings.bocha_api_key}"}
        payload = {"query": query, "limit": limit}
        response = requests.post(settings.bocha_base_url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", []) if isinstance(data, dict) else []
        return [self._to_doc(topic_id, i) for i in items if i.get("content")]

    @staticmethod
    def _to_doc(topic_id: str, item: dict[str, Any]) -> UnifiedDoc:
        raw_id = str(item.get("id") or item.get("url") or item.get("title") or "bocha")
        return UnifiedDoc(
            doc_id=f"bocha:{raw_id}",
            topic_id=topic_id,
            source_type="bocha",
            source_name="bocha",
            title=item.get("title"),
            content=item.get("content", ""),
            url=item.get("url"),
            author=item.get("author"),
            credibility_hint="external",
        )
