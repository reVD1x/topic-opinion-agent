from __future__ import annotations

from app.agents.sentiment_agent import SentimentAgent


def test_fallback_all_neutral_when_llm_disabled(mock_llm, sample_docs):
    agent = SentimentAgent(mock_llm)
    result = agent.run(sample_docs)
    assert len(result) == len(sample_docs)
    for item in result:
        assert item.label == "neutral"
        assert item.confidence == 0.5


def test_empty_docs_returns_empty(mock_llm):
    agent = SentimentAgent(mock_llm)
    result = agent.run([])
    assert result == []
