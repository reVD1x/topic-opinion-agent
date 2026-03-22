from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SentimentItem(BaseModel):
    doc_id: str
    label: Literal["positive", "neutral", "negative"]
    confidence: float


class OpinionSummary(BaseModel):
    supports: list[str]
    opposes: list[str]
    neutrals: list[str]
    controversy_points: list[str]


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
