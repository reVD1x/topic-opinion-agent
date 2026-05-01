from __future__ import annotations

from unittest.mock import patch

from app.agents.opinion_agent import OpinionAgent


def test_fallback_placeholder_when_llm_disabled(mock_llm, sample_docs):
    agent = OpinionAgent(mock_llm)
    result = agent.run("test_topic", sample_docs)
    assert len(result.supports) >= 1
    assert len(result.opposes) >= 1
    assert len(result.neutrals) >= 1
    assert len(result.controversy_points) >= 1


def test_fallback_on_empty_dict_response(sample_docs):
    """LLM enabled but chat_json returns {} → fallback to placeholder opinions."""
    from app.llm.gateway import LLMGateway
    llm = LLMGateway()
    llm.enabled = True
    with patch.object(llm, "chat_json", return_value={}):
        agent = OpinionAgent(llm)
        result = agent.run("test_topic", sample_docs)
        assert len(result.supports) >= 1
        assert len(result.opposes) >= 1
        assert len(result.neutrals) >= 1
        assert len(result.controversy_points) >= 1


def test_empty_docs_returns_empty(mock_llm):
    agent = OpinionAgent(mock_llm)
    result = agent.run("test_topic", [])
    assert len(result.supports) == 0
    assert len(result.opposes) == 0
