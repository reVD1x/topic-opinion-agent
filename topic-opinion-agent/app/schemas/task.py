from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TopicAnalysisRequest(BaseModel):
    topic_id: str
    target_date: Optional[date] = None
    enable_forecast: bool = False
    use_external: bool = True


class TopicAnalysisTask(BaseModel):
    task_id: str
    topic_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    message: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
