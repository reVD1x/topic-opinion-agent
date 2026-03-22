from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.analysis import ForecastResult, OpinionSummary, RiskResult, SentimentItem


class EvidenceItem(BaseModel):
    doc_id: str
    source_type: str
    title: Optional[str] = None
    url: Optional[str] = None


class TopicReport(BaseModel):
    topic_id: str
    overview: str
    source_distribution: dict[str, int]
    sentiment_summary: dict[str, int]
    sentiment_items: list[SentimentItem]
    opinion_blocks: OpinionSummary
    risk: RiskResult
    evidence_list: list[EvidenceItem]
    forecast: Optional[ForecastResult] = None
    module_summaries: dict[str, str] = Field(default_factory=dict)
    markdown: str
