"""观点抽取 Agent — 基于 LLM 的观点阵营分析与证据追溯。"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from app.common.constants import OPINION_MAX_DOCS, OPINION_SNIPPET_LEN
from app.common.utils import ts
from app.llm.gateway import LLMGateway
from app.schemas.analysis import OpinionPoint, OpinionSummary
from app.schemas.doc import UnifiedDoc

logger = logging.getLogger(__name__)


class OpinionAgent:
    """从文档集合中抽取观点阵营：支持、反对、中立、争议焦点。

    每个观点点附带 evidence_ids 以实现证据追溯。LLM 不可用时返回占位观点。
    """

    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(
        self,
        topic_id: str,
        docs: list[UnifiedDoc],
        log_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> OpinionSummary:
        """抽取观点阵营。

        Args:
            topic_id: 话题标识。
            docs: 待分析的文档列表。
            log_callback: 可选进度回调。

        Returns:
            包含四个阵营（supports/opposes/neutrals/controversy_points）的 OpinionSummary。
        """
        if not docs:
            return OpinionSummary()

        n_docs = len(docs)
        logger.info("开始观点抽取，共 %d 条文档", n_docs)
        if log_callback:
            log_callback({"ts": ts(), "msg": f"开始观点抽取，共 {n_docs} 条文档"})

        if not self.llm.enabled:
            logger.info("LLM 未启用，使用占位观点")
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 未启用，使用占位观点"})
            return OpinionSummary(
                supports=[OpinionPoint(content="样本中存在支持性表达")],
                opposes=[OpinionPoint(content="样本中存在质疑性表达")],
                neutrals=[OpinionPoint(content="样本中存在事实转述")],
                controversy_points=[OpinionPoint(content="核心争议尚不明确，需补充语料")],
            )

        target_docs = docs[:OPINION_MAX_DOCS]
        # Map short integer IDs → real doc_id so the LLM never sees long URL-based IDs.
        id_map: dict[str, str] = {str(i): d.doc_id for i, d in enumerate(target_docs)}
        lines: list[str] = []
        for i, d in enumerate(target_docs):
            lines.append(f"[{i}]: {d.content[:OPINION_SNIPPET_LEN]}")
        joined = "\n".join(lines)

        logger.info("LLM 调用中（%d 条输入）", min(n_docs, OPINION_MAX_DOCS))
        if log_callback:
            log_callback({"ts": ts(), "msg": f"LLM 调用中（{min(n_docs, OPINION_MAX_DOCS)} 条输入）…"})

        rsp = self.llm.chat_json(
            system_prompt=(
                "你是一个中文舆情观点分析师。请按照以下步骤进行推理：\n\n"
                "核心原则：支持/反对立场必须以【话题主体】为参照系。\n"
                "- 文档中的观点对话题主体有利、赞赏、维护 → supports（支持）\n"
                "- 文档中的观点对话题主体不利、批评、攻击 → opposes（反对）\n"
                "- 文档仅做事实转述、无明显立场，或立场与话题主体无关 → neutrals（中立）\n"
                "- 多种对立观点激烈碰撞、争议焦点明确 → controversy_points（争议焦点）\n\n"
                "注意：不要被文中提及的其他不相干话题或主体干扰。\n\n"
                "分析步骤：\n"
                "1. 阅读所有文档，识别其中的主要观点、态度和论点。\n"
                "2. 将相似立场归入同一观点阵营。每个阵营最多5条观点，优先选择质量最高的。\n"
                "3. 每条观点必须有证据支撑——请填写 evidence_ids 引用对应文档的编号。"
                "没有文档支撑的观点必须丢弃。\n"
                "4. 每条输入行以 [数字]: 内容 开头，请使用这些数字作为 evidence_ids。\n\n"
                "输出JSON格式：\n"
                '{"supports": [{content: string, evidence_ids: [string], reasoning: string}, ...],\n'
                ' "opposes": [{content: string, evidence_ids: [string], reasoning: string}, ...],\n'
                ' "neutrals": [{content: string, evidence_ids: [string], reasoning: string}, ...],\n'
                ' "controversy_points": [{content: string, evidence_ids: [string], reasoning: string}, ...]}\n\n'
                "规则：\n"
                "- 每条观点用一句话概括（中文），简洁明确。\n"
                "- evidence_ids 必须严格使用输入行的 [数字] 编号（如 \"0\"、\"1\"），不加括号。\n"
                "- 每条观点输出项必须包含 reasoning 字段，简要解释推理过程。\n"
                "- 每个阵营最多5条观点。\n"
                "- 若某阵营缺少相关文档，返回空列表 []。"
            ),
            user_prompt=f"话题：{topic_id}\n\n{joined}",
        )

        if not isinstance(rsp, dict):
            logger.warning("LLM 返回格式异常，回退为占位观点")
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 返回格式异常，回退为占位观点"})
            return OpinionSummary(
                supports=[OpinionPoint(content="样本中存在支持性表达")],
                opposes=[OpinionPoint(content="样本中存在质疑性表达")],
                neutrals=[OpinionPoint(content="样本中存在事实转述")],
                controversy_points=[OpinionPoint(content="核心争议尚不明确，需补充语料")],
            )

        supports = self._parse_opinions(rsp.get("supports"), id_map)
        opposes = self._parse_opinions(rsp.get("opposes"), id_map)
        neutrals = self._parse_opinions(rsp.get("neutrals"), id_map)
        controversy = self._parse_opinions(rsp.get("controversy_points"), id_map)

        # LLM 返回了有效 dict 但所有阵营为空 → 视为回退
        if not any((supports, opposes, neutrals, controversy)):
            logger.warning("LLM 返回空阵营，回退为占位观点")
            if log_callback:
                log_callback({"ts": ts(), "msg": "LLM 返回空阵营，回退为占位观点"})
            return OpinionSummary(
                supports=[OpinionPoint(content="样本中存在支持性表达")],
                opposes=[OpinionPoint(content="样本中存在质疑性表达")],
                neutrals=[OpinionPoint(content="样本中存在事实转述")],
                controversy_points=[OpinionPoint(content="核心争议尚不明确，需补充语料")],
            )

        logger.info(
            "完成：支持%d，反对%d，中立%d，争议%d",
            len(supports), len(opposes), len(neutrals), len(controversy),
        )
        if log_callback:
            log_callback({
                "ts": ts(),
                "msg": (
                    f"完成：支持{len(supports)}，反对{len(opposes)}，"
                    f"中立{len(neutrals)}，争议{len(controversy)}"
                ),
            })

        return OpinionSummary(
            supports=supports,
            opposes=opposes,
            neutrals=neutrals,
            controversy_points=controversy,
        )

    @staticmethod
    def _parse_opinions(
        raw: object, id_map: dict[str, str]
    ) -> list[OpinionPoint]:
        """解析 LLM 返回的原始观点列表，将短 ID 映射回真实 doc_id。

        Args:
            raw: LLM 返回的原始 JSON 列表。
            id_map: 短 ID → 真实 doc_id 的映射。

        Returns:
            过滤并去重后的 OpinionPoint 列表（最多 5 条）。
        """
        if not isinstance(raw, list):
            return []
        parsed: list[OpinionPoint] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            raw_ids = item.get("evidence_ids", [])
            if not isinstance(raw_ids, list):
                raw_ids = []
            evidence_ids: list[str] = []
            for eid in raw_ids:
                # Normalize: strip brackets, whitespace; handle both str and int
                normalized = str(eid).strip().lstrip("[").rstrip("]").strip()
                real_id = id_map.get(normalized)
                if real_id:
                    evidence_ids.append(real_id)
                else:
                    logger.debug("观点分析：evidence_id=%s 无法映射到证据文档，已跳过", str(eid)[:40])
            if not evidence_ids:
                continue
            reasoning = str(item.get("reasoning", "")).strip()
            parsed.append(OpinionPoint(content=content, evidence_ids=evidence_ids, reasoning=reasoning))
        return parsed[:5]
