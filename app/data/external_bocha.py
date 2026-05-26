from __future__ import annotations

import json
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

        # Bocha API returns {messages: [{type: "source", content: "{value: [...]}"}]}
        results: list[dict[str, Any]] = []
        for msg in data.get("messages", []) or []:
            if msg.get("type") != "source":
                continue
            raw_content = msg.get("content", "")
            if isinstance(raw_content, str):
                try:
                    raw_content = json.loads(raw_content)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(raw_content, list):
                items = raw_content
            else:
                items = raw_content.get("value", []) or [] if isinstance(raw_content, dict) else []
            for item in items:
                if item.get("name") or item.get("snippet"):
                    results.append(item)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return [self._to_doc(topic_id, r) for r in results]

    @staticmethod
    def _to_doc(topic_id: str, item: dict[str, Any]) -> UnifiedDoc:
        raw_id = str(item.get("id") or item.get("url") or item.get("name") or "bocha")
        return UnifiedDoc(
            doc_id=f"bocha:{raw_id}",
            topic_id=topic_id,
            source_type="bocha",
            source_name="bocha",
            title=item.get("name"),
            content=item.get("snippet") or item.get("summary") or "",
            url=item.get("url"),
            author=item.get("author"),
            credibility_hint="external",
        )
