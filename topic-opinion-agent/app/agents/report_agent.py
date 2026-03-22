from __future__ import annotations

from typing import Any

from app.llm.gateway import LLMGateway
from app.schemas.analysis import ForecastResult, OpinionSummary, RiskResult, SentimentItem
from app.schemas.doc import UnifiedDoc
from app.schemas.report import EvidenceItem, TopicReport


RISK_LEVEL_MAP = {"high": "高", "medium": "中", "low": "低"}
TREND_MAP = {"rise": "上升", "flat": "平稳", "fall": "下降"}
UNCERTAINTY_MAP = {"high": "高", "medium": "中", "low": "低"}
TIME_HORIZON_MAP = {"24h": "24 小时", "72h": "72 小时"}
MODULE_NAME_MAP = {
    "collect": "数据采集",
    "preprocess": "数据预处理",
    "sentiment": "情感分析",
    "opinion": "观点抽取",
    "risk": "风险研判",
    "forecast": "趋势预测",
    "report": "报告生成",
}


def _to_cn(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value)


class ReportAgent:
    def __init__(self, llm: LLMGateway) -> None:
        self.llm = llm

    def run(
        self,
        topic_id: str,
        docs: list[UnifiedDoc],
        source_distribution: dict[str, int],
        sentiments: list[SentimentItem],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
    ) -> TopicReport:
        summary = {"positive": 0, "neutral": 0, "negative": 0}
        for s in sentiments:
            summary[s.label] += 1

        evidence = [
            EvidenceItem(doc_id=d.doc_id, source_type=d.source_type, title=d.title, url=d.url)
            for d in docs[:50]
        ]
        module_summaries = self._build_module_summaries(
            docs=docs,
            source_distribution=source_distribution,
            sentiment_summary=summary,
            opinions=opinions,
            risk=risk,
            forecast=forecast,
            evidence_count=len(evidence),
        )
        md = self._build_markdown(topic_id, source_distribution, summary, opinions, risk, forecast, module_summaries)

        return TopicReport(
            topic_id=topic_id,
            overview=f"样本总量 {len(docs)}，覆盖 {len(source_distribution)} 类来源。",
            source_distribution=source_distribution,
            sentiment_summary=summary,
            sentiment_items=sentiments,
            opinion_blocks=opinions,
            risk=risk,
            evidence_list=evidence,
            forecast=forecast,
            module_summaries=module_summaries,
            markdown=md,
        )

    def _build_module_summaries(
        self,
        docs: list[UnifiedDoc],
        source_distribution: dict[str, int],
        sentiment_summary: dict[str, int],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        evidence_count: int,
    ) -> dict[str, str]:
        top_source = "unknown"
        if source_distribution:
            top_source = max(source_distribution.items(), key=lambda item: item[1])[0]

        summaries: dict[str, str] = {}
        module_contexts: dict[str, dict[str, Any]] = {
            "collect": {
                "doc_count": len(docs),
                "source_types": len(source_distribution),
                "top_source": top_source,
            },
            "preprocess": {
                "doc_count_after_clean": len(docs),
                "has_content": any(bool(d.content) for d in docs),
            },
            "sentiment": sentiment_summary,
            "opinion": {
                "supports": len(opinions.supports),
                "opposes": len(opinions.opposes),
                "neutrals": len(opinions.neutrals),
                "controversy_points": len(opinions.controversy_points),
            },
            "risk": {
                "risk_level": risk.risk_level,
                "trigger_count": len(risk.triggers),
                "evidence_count": len(risk.evidence_ids),
            },
            "forecast": (
                {
                    "enabled": True,
                    "trend": forecast.trend_judgement,
                    "horizon": forecast.time_horizon,
                    "uncertainty": forecast.uncertainty,
                }
                if forecast
                else {"enabled": False}
            ),
            "report": {
                "evidence_items": evidence_count,
                "contains_forecast": forecast is not None,
            },
        }

        for module_name, context in module_contexts.items():
            summaries[module_name] = self._summarize_module(module_name, context)

        return summaries

    def _summarize_module(self, module_name: str, context: dict[str, Any]) -> str:
        if not self.llm.enabled:
            return f"{module_name}模块已完成，关键信息：{context}"

        rsp = self.llm.chat_json(
            system_prompt=(
                "你是舆情分析流水线助手。"
                "请基于给定模块信息生成1-2句中文总结，控制在60字内。"
                "输出JSON: {summary:string}。"
            ),
            user_prompt=f"module={module_name}\ncontext={context}",
        )
        summary = rsp.get("summary") if isinstance(rsp, dict) else None
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        return f"{module_name}模块已完成，关键信息：{context}"

    @staticmethod
    def _build_markdown(
        topic_id: str,
        source_distribution: dict[str, int],
        sentiment_summary: dict[str, int],
        opinions: OpinionSummary,
        risk: RiskResult,
        forecast: ForecastResult | None,
        module_summaries: dict[str, str],
    ) -> str:
        lines = [f"# 话题分析报告：{topic_id}", "", "## 来源分布"]

        if source_distribution:
            lines.extend(["| 来源类型 | 数量 |", "| --- | ---: |"])
            for source, count in sorted(source_distribution.items(), key=lambda item: item[1], reverse=True):
                lines.append(f"| {source} | {count} |")
        else:
            lines.append("- 无来源数据")

        lines.extend(["", "## 情感统计", "| 情感倾向 | 数量 |", "| --- | ---: |"])
        lines.append(f"| 正向 | {sentiment_summary.get('positive', 0)} |")
        lines.append(f"| 中性 | {sentiment_summary.get('neutral', 0)} |")
        lines.append(f"| 负向 | {sentiment_summary.get('negative', 0)} |")

        lines.extend(["", "## 观点阵营", "### 支持观点"])
        lines.extend([f"- {item}" for item in opinions.supports] or ["- 无"])

        lines.extend(["", "### 反对观点"])
        lines.extend([f"- {item}" for item in opinions.opposes] or ["- 无"])

        lines.extend(["", "### 中立观点"])
        lines.extend([f"- {item}" for item in opinions.neutrals] or ["- 无"])

        lines.extend(["", "### 争议焦点"])
        lines.extend([f"- {item}" for item in opinions.controversy_points] or ["- 无"])

        lines.extend(["", "## 风险研判", f"- 风险等级：{_to_cn(RISK_LEVEL_MAP, risk.risk_level)}", "- 触发因素："])
        lines.extend([f"  - {item}" for item in risk.triggers] or ["  - 无"])

        lines.append("- 证据 ID（最多 10 条）：")
        lines.extend([f"  - `{doc_id}`" for doc_id in risk.evidence_ids[:10]] or ["  - 无"])

        lines.extend(["", "## 模块总结"])
        for module_name, summary in module_summaries.items():
            lines.append(f"- {_to_cn(MODULE_NAME_MAP, module_name)}：{summary}")

        if forecast:
            lines.extend(
                [
                    "",
                    "## 趋势预测（仅基于 LLM 推断）",
                    f"- 趋势判断：{_to_cn(TREND_MAP, forecast.trend_judgement)}",
                    f"- 时间窗：{_to_cn(TIME_HORIZON_MAP, forecast.time_horizon)}",
                    "- 关键假设：",
                ]
            )
            lines.extend([f"  - {item}" for item in forecast.assumptions] or ["  - 无"])

            lines.append("- 反事实：")
            lines.extend([f"  - {item}" for item in forecast.counterfactuals] or ["  - 无"])

            lines.extend(
                [
                    f"- 不确定性：{_to_cn(UNCERTAINTY_MAP, forecast.uncertainty)}",
                    f"- 说明：{forecast.disclaimer}",
                ]
            )

        return "\n".join(lines)
