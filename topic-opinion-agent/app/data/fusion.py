from __future__ import annotations

from collections.abc import Iterable

from app.schemas.doc import UnifiedDoc


class DataFusionService:
    def merge_and_dedup(self, docs: Iterable[UnifiedDoc]) -> list[UnifiedDoc]:
        deduped: dict[str, UnifiedDoc] = {}
        for doc in docs:
            key = self._dedup_key(doc)
            if key not in deduped:
                deduped[key] = doc
        return sorted(
            deduped.values(),
            key=lambda x: x.publish_time.isoformat() if x.publish_time else "",
        )

    @staticmethod
    def source_distribution(docs: list[UnifiedDoc]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for doc in docs:
            counts[doc.source_type] = counts.get(doc.source_type, 0) + 1
        return counts

    @staticmethod
    def _dedup_key(doc: UnifiedDoc) -> str:
        if doc.url:
            return f"url::{doc.url}"
        if doc.title:
            return f"title::{doc.title.strip().lower()}"
        return f"content::{doc.content[:80].strip().lower()}"
