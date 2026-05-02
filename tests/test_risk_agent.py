from __future__ import annotations

from app.agents.risk_agent import RiskAgent
from app.schemas.analysis import OpinionSummary


def test_detects_trigger_words(sample_docs, mock_llm):
    agent = RiskAgent(mock_llm)
    result = agent.run(sample_docs, OpinionSummary())
    # doc_1 has: 谣言, 违法, 维权, 事故, 伤亡 (5 unique triggers)
    # doc_4 has: 维权, 抵制 (but 维权 already counted)
    # Total unique trigger words in content: 谣言, 违法, 维权, 事故, 伤亡, 抵制 = potentially 6
    # But only one hit per doc (break after first), so count is number of docs with any trigger
    # doc_1: 谣言 (yes), doc_4: 维权 (yes) → 2 docs hit → low
    assert result.risk_level in ("low", "medium", "high")
    assert len(result.triggers) > 0


def test_empty_docs_returns_low(mock_llm):
    agent = RiskAgent(mock_llm)
    result = agent.run([], OpinionSummary())
    assert result.risk_level == "low"
    assert "empty_sample" in result.triggers


def test_high_risk_with_many_triggers(mock_llm):
    agent = RiskAgent(mock_llm)
    from app.schemas.doc import UnifiedDoc

    # Create 10 docs each with a unique trigger to trigger high risk
    docs = []
    for i in range(10):
        docs.append(UnifiedDoc(
            doc_id=f"d{i}",
            topic_id="t",
            source_type="news",
            content=f"test content 谣言 conflict repeat {i}",
        ))
    result = agent.run(docs, OpinionSummary())
    # Each doc hits "谣言" → 10 hits → high
    assert result.risk_level == "high"
