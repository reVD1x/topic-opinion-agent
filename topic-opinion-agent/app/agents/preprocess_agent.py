from __future__ import annotations

from app.schemas.doc import UnifiedDoc


class PreprocessAgent:
    def run(self, docs: list[UnifiedDoc]) -> list[UnifiedDoc]:
        seen: set[str] = set()
        cleaned: list[UnifiedDoc] = []

        for doc in docs:
            content = (doc.content or "").strip()
            if not content:
                continue

            key = f"{doc.title or ''}::{content[:120]}"
            if key in seen:
                continue
            seen.add(key)

            if len(content) > 2000:
                doc.content = content[:2000]
            else:
                doc.content = content
            cleaned.append(doc)

        return cleaned
