from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SentimentItem(BaseModel):
    doc_id: str
    label: Literal["positive", "neutral", "negative"]
    confidence: float
    reasoning: str = ""


class OpinionPoint(BaseModel):
    """A single opinion point with evidence traceability."""
    content: str
    evidence_ids: list[str] = Field(default_factory=list, description="doc_id references backing this opinion")
    reasoning: str = ""


class OpinionSummary(BaseModel):
    supports: list[OpinionPoint] = Field(default_factory=list)
    opposes: list[OpinionPoint] = Field(default_factory=list)
    neutrals: list[OpinionPoint] = Field(default_factory=list)
    controversy_points: list[OpinionPoint] = Field(default_factory=list)


class RiskResult(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    triggers: list[str]
    evidence_ids: list[str]


class ForecastResult(BaseModel):
    forecast_type: Literal["llm_inference_only"] = "llm_inference_only"
    trend_judgement: Literal["rise", "flat", "fall"]
    time_horizon: Literal["24h", "72h"]
    assumptions: list[str]
    counterfactuals: list[str]
    uncertainty: Literal["low", "medium", "high"]
    disclaimer: str
    reasoning: str = ""
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="doc_id references that inform the forecast reasoning",
    )
