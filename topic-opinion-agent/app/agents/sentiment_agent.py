"""情感分析 Agent — 基于 LLM 的情感三分类（正向/中性/负向）。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.common.constants import SENTIMENT_MAX_DOCS, SENTIMENT_SNIPPET_LEN
from app.common.utils import ts
from app.llm.gateway import LLMGateway
from app.schemas.analysis import SentimentItem
from app.schemas.doc import UnifiedDoc

logger = logging.getLogger(__name__)


class SentimentAgent:
    """对文档列表进行情感分析，逐条标注 positive/neutral/negative。

    LLM 不可用时回退为全部 neutral（置信度 0.5）。
    """

    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(
        self,
        docs: list[UnifiedDoc],
        topic_id: str = "",
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[SentimentItem]:
        """分析文档情感倾向。

        Args:
            docs: 待分析的文档列表。
            topic_id: 目标话题名称，用于将分析与话题紧密关联。
            log_callback: 可选进度回调。

        Returns:
            与输入文档一一对应的 SentimentItem 列表。
        """
        if not docs:
            return []

        logger.info("开始情感分析，共 %d 条文档", len(docs))
        if log_callback:
            log_callback({"ts": ts(), "msg": f"开始情感分析，共 {len(docs)} 条文档"})

        if not self.llm.enabled:
            logger.info("LLM 未启用，回退为全部中性")
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 未启用，使用启发式回退（全部标记为中性）"})
            return [
                SentimentItem(doc_id=d.doc_id, label="neutral", confidence=0.5)
                for d in docs
            ]

        target_docs = docs[:SENTIMENT_MAX_DOCS]
        # Map short integer IDs → real doc_id so the LLM never sees long URL-based IDs.
        id_map: dict[str, str] = {str(i): d.doc_id for i, d in enumerate(target_docs)}
        prompt = "\n".join(
            [f"[{i}]: {d.content[:SENTIMENT_SNIPPET_LEN]}" for i, d in enumerate(target_docs)]
        )
        logger.info("LLM 调用中（%d 条输入）", len(target_docs))
        if log_callback:
            log_callback({"ts": ts(), "msg": f"LLM 调用中（{len(target_docs)} 条输入）…"})

        topic_context = f"话题：{topic_id}\n\n" if topic_id else ""
        rsp = self.llm.chat_json(
            system_prompt=(
                "你是一个中文舆情情感分析师。请针对当前话题，对每条文档进行情感推理：\n"
                "1. 情感信号 — 文档使用了哪些情感语言、语气或修辞？\n"
                "2. 对话题的立场 — 内容是对该话题持支持、反对还是中立态度？"
                "注意区分讨论该话题本身的态度，不要被文中提及的其他不相干话题干扰。\n"
                "3. 置信度 — 情感判断是明确还是模糊？\n\n"
                "完成推理后，逐条分类。"
                "输出JSON: {items:[{doc_id,label,confidence,reasoning}]}。"
                "doc_id 必须使用输入行开头的 [数字] 前缀。"
                "label 取 positive/neutral/negative。confidence 0.0-1.0。"
                "reasoning 字段需用中文简要解释你的分析过程（20字内）。"
            ),
            user_prompt=topic_context + prompt,
        )
        items = rsp.get("items", []) if isinstance(rsp, dict) else []
        parsed: list[SentimentItem] = []
        for item in items:
            try:
                short_id = str(item.get("doc_id", ""))
                real_id = id_map.get(short_id)
                if real_id:
                    item["doc_id"] = real_id
                # If short_id not in map, keep as-is and let evidence chain flag it
                parsed.append(SentimentItem(**item))
            except Exception:
                logger.warning("情感分析：跳过无法解析的条目 %s", str(item)[:80])
                continue
        if not parsed:
            logger.warning("LLM 解析失败，回退为全部中性")
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 解析失败，回退为全部中性"})
            parsed = [SentimentItem(doc_id=d.doc_id, label="neutral", confidence=0.5) for d in docs]
        else:
            if log_callback:
                log_callback({"ts": ts(), "msg": f"LLM 返回 {len(items)} 条，成功解析 {len(parsed)} 条"})

        pos = sum(1 for s in parsed if s.label == "positive")
        neu = sum(1 for s in parsed if s.label == "neutral")
        neg = sum(1 for s in parsed if s.label == "negative")
        logger.info("完成：正向%d，中性%d，负向%d", pos, neu, neg)
        if log_callback:
            log_callback({"ts": ts(), "msg": f"完成：正向{pos}，中性{neu}，负向{neg}"})

        return parsed
