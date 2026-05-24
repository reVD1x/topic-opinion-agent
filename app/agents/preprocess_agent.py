"""数据预处理 Agent — 去重、空内容移除、长文本截断、话题相关性过滤。"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from app.common.constants import CONTENT_TRUNCATE_LEN, DEDUP_KEY_LEN
from app.common.utils import ts
from app.schemas.doc import UnifiedDoc

logger = logging.getLogger(__name__)

_RELEVANCE_SYSTEM_PROMPT = """你是一个数据清洗助手。你的任务是判断文档是否与指定话题**有关联**。

宽松标准：
- 文档提及该话题，即使不是核心主题也视为相关
- 话题作为国家/地区时：文档提及该国产品、企业、人物、文化元素均可视为相关
- 话题作为事件/品牌时：文档涉及该事件/品牌的任何方面均可视为相关
- 仅当文档与该话题完全无关时才判定为不相关

不相关示例（极少数情况）：
- 话题="日本"，文档="霸王茶姬免单活动"（完全无关）

返回JSON格式，仅包含relevant_ids列表：
{"relevant_ids": [0, 1, 2, 3, 5]}"""


class PreprocessAgent:
    """文档预处理：话题相关性过滤 → 去重（按标题+前N字符）→ 移除空内容 → 截断超长文本。

    无状态，可跨 pipeline 复用。话题过滤依赖 LLM。
    """

    def run(
        self,
        docs: list[UnifiedDoc],
        log_callback: Callable[[dict[str, Any]], None] | None = None,
        topic_id: str | None = None,
        llm: Any = None,
    ) -> list[UnifiedDoc]:
        """执行预处理并返回清洗后的文档列表。

        Args:
            docs: 原始 UnifiedDoc 列表。
            log_callback: 可选，接收 ``{"ts": str, "msg": str}`` 的进度回调。
            topic_id: 可选，目标话题名称，用于相关性过滤。
            llm: 可选，LLM 网关实例，用于话题相关性判断。

        Returns:
            过滤、去重、非空、截断后的文档列表。
        """
        n_input = len(docs)
        logger.info("开始预处理，输入 %d 条", n_input)
        if log_callback:
            log_callback({"ts": ts(), "msg": f"开始预处理，输入 {n_input} 条"})

        # ── Step 0: topic relevance filter ──
        if topic_id and llm and llm.enabled and docs:
            docs = self._filter_by_topic_relevance(docs, topic_id, llm, log_callback)

        # ── Step 1-3: dedup, empty remove, truncate ──
        seen: set[str] = set()
        cleaned: list[UnifiedDoc] = []
        dupes = 0
        empty = 0
        truncated = 0

        for doc in docs:
            content = (doc.content or "").strip()
            if not content:
                empty += 1
                continue

            key = f"{doc.title or ''}::{content[:DEDUP_KEY_LEN]}"
            if key in seen:
                dupes += 1
                continue
            seen.add(key)

            if len(content) > CONTENT_TRUNCATE_LEN:
                doc.content = content[:CONTENT_TRUNCATE_LEN]
                truncated += 1
            else:
                doc.content = content
            cleaned.append(doc)

        parts: list[str] = []
        if dupes:
            parts.append(f"去重 {dupes} 条")
        if empty:
            parts.append(f"空内容 {empty} 条")
        if truncated:
            parts.append(f"截断 {truncated} 条")
        detail = "，".join(parts) if parts else "无变更"
        logger.info("预处理完成：%s，保留 %d 条", detail, len(cleaned))
        if log_callback:
            log_callback({"ts": ts(), "msg": f"预处理完成：{detail}，保留 {len(cleaned)} 条"})

        return cleaned

    # ── topic relevance filter ──────────────────────────────────────
    @staticmethod
    def _filter_by_topic_relevance(
        docs: list[UnifiedDoc],
        topic_id: str,
        llm: Any,
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[UnifiedDoc]:
        """Batch LLM call to filter docs by topic relevance.

        Returns only docs that the LLM considers genuinely about *topic_id*.
        """
        logger.info("话题相关性过滤：%d 条 -> 话题[%s]", len(docs), topic_id)

        # Build candidate list with index
        candidates: list[dict[str, Any]] = []
        doc_list: list[str] = []
        for i, doc in enumerate(docs):
            title = doc.title or ""
            snippet = (doc.content or "")[:200].replace("\n", " ")
            doc_list.append(f"[{i}] 来源:{doc.source_type} | 标题:{title} | 摘要:{snippet}")
            candidates.append({"idx": i, "doc": doc})

        user_message = f'话题："{topic_id}"\n\n请判断以下文档是否与该话题真正相关：\n\n' + "\n".join(doc_list)

        try:
            result = llm.chat_json(
                system_prompt=_RELEVANCE_SYSTEM_PROMPT,
                user_prompt=user_message,
            )
            relevant_ids: set[int] = set(result.get("relevant_ids", []))
        except Exception:
            logger.exception("话题相关性过滤失败，放行全部文档")
            return docs  # fallback: pass all through

        filtered = [c["doc"] for c in candidates if c["idx"] in relevant_ids]
        removed = len(docs) - len(filtered)
        logger.info("相关性过滤完成：保留 %d/%d 条（移除 %d 条不相关）", len(filtered), len(docs), removed)
        if log_callback:
            log_callback({"ts": ts(), "msg": f"话题相关性过滤：保留 {len(filtered)}/{len(docs)} 条（移除 {removed} 条不相关）"})

        if not filtered:
            logger.warning("相关性过滤后无剩余文档，放行原始文档")
            return docs

        return filtered
