from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.doc import UnifiedDoc


class AgentResult(BaseModel):
    name: str
    success: bool
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class GraphState(BaseModel):
    task_id: str
    topic_id: str
    target_date: date | None = None
    docs: list[UnifiedDoc] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    results: list[AgentResult] = Field(default_factory=list)
