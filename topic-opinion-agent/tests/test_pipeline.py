from __future__ import annotations

import pytest

from app.workflow.pipeline import TopicAnalysisPipeline


def test_pipeline_construction():
    pipeline = TopicAnalysisPipeline()
    assert pipeline.llm is not None
    assert pipeline.preprocess_agent is not None
    assert pipeline.sentiment_agent is not None
    assert pipeline.opinion_agent is not None
    assert pipeline.risk_agent is not None
    assert pipeline.forecast_agent is not None
    assert pipeline.report_agent is not None
