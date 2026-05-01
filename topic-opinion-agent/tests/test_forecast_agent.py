from __future__ import annotations

from app.agents.forecast_agent import ForecastAgent


def test_default_forecast_when_llm_disabled(mock_llm, sample_docs):
    agent = ForecastAgent(mock_llm)
    result = agent.run(sample_docs)
    assert result.trend_judgement == "flat"
    assert result.uncertainty == "high"
    assert len(result.assumptions) >= 1
    assert len(result.evidence_ids) > 0


def test_empty_docs_default_forecast(mock_llm):
    agent = ForecastAgent(mock_llm)
    result = agent.run([])
    assert result.trend_judgement == "flat"
