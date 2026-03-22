from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UnifiedDoc(BaseModel):
    doc_id: str = Field(description="Unique id used by evidence tracing")
    topic_id: str
    source_type: str = Field(description="news/platform/bocha/tavily")
    source_name: Optional[str] = None
    title: Optional[str] = None
    content: str
    publish_time: Optional[datetime] = None
    url: Optional[str] = None
    author: Optional[str] = None
    engagement: Optional[int] = None
    credibility_hint: Optional[str] = None
