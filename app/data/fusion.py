from __future__ import annotations

from collections.abc import Iterable

from app.schemas.doc import UnifiedDoc

# DB table name → Chinese display name for platform source distribution
_PLATFORM_TABLE_TO_CN: dict[str, str] = {
    "xhs_note": "小红书", "douyin_aweme": "抖音", "kuaishou_video": "快手",
    "bilibili_video": "B站", "weibo_note": "微博", "tieba_note": "贴吧", "zhihu_content": "知乎",
}


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
        """返回按来源（中文）分组的文档数量。

        - 新闻类文档按 source_name 分组，未知来源退回 "新闻"
        - 平台类文档按中文平台名分组（如 小红书、抖音）
        """
        counts: dict[str, int] = {}
        for doc in docs:
            if doc.source_type == "platform" and doc.source_name:
                key = _PLATFORM_TABLE_TO_CN.get(doc.source_name, doc.source_name)
            elif doc.source_type == "news":
                key = doc.source_name or "新闻"
            else:
                key = doc.source_type
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _dedup_key(doc: UnifiedDoc) -> str:
        if doc.url:
            return f"url::{doc.url}"
        if doc.title:
            return f"title::{doc.title.strip().lower()}"
        return f"content::{doc.content[:80].strip().lower()}"
