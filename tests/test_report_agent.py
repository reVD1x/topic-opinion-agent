from __future__ import annotations

from app.agents.report_agent import ReportAgent
from app.schemas.analysis import (
    ForecastResult,
    OpinionPoint,
    OpinionSummary,
    RiskResult,
    SentimentItem,
)


def test_generates_report_with_all_fields(mock_llm, sample_docs):
    agent = ReportAgent(mock_llm)
    sentiments = [
        SentimentItem(doc_id=d.doc_id, label="neutral", confidence=0.5)
        for d in sample_docs
    ]
    opinions = OpinionSummary(
        supports=[OpinionPoint(content="支持观点", evidence_ids=["doc_2"])],
        opposes=[OpinionPoint(content="反对观点", evidence_ids=["doc_1"])],
        neutrals=[OpinionPoint(content="中立", evidence_ids=["doc_3"])],
        controversy_points=[OpinionPoint(content="争议", evidence_ids=["doc_1", "doc_4"])],
    )
    risk = RiskResult(risk_level="medium", triggers=["谣言", "维权"], evidence_ids=["doc_1", "doc_4"])
    forecast = ForecastResult(
        trend_judgement="flat",
        time_horizon="24h",
        assumptions=["无新增重大事件"],
        counterfactuals=["出现通报将改变趋势"],
        uncertainty="high",
        disclaimer="测试",
        evidence_ids=["doc_1"],
    )

    result = agent.run(
        topic_id="test_topic",
        docs=sample_docs,
        source_distribution={"news": 3, "platform": 2},
        sentiments=sentiments,
        opinions=opinions,
        risk=risk,
        forecast=forecast,
    )

    assert result.topic_id == "test_topic"
    assert result.source_distribution == {"news": 3, "platform": 2}
    assert result.sentiment_summary["positive"] == 0
    assert result.risk.risk_level == "medium"
    assert len(result.evidence_list) > 0
    assert len(result.markdown) > 0
    assert len(result.module_summaries) > 0


def test_report_without_forecast(mock_llm, sample_docs):
    agent = ReportAgent(mock_llm)
    sentiments = [
        SentimentItem(doc_id=d.doc_id, label="neutral", confidence=0.5)
        for d in sample_docs
    ]
    risk = RiskResult(risk_level="low", triggers=[], evidence_ids=[])

    result = agent.run(
        topic_id="test_topic",
        docs=sample_docs,
        source_distribution={},
        sentiments=sentiments,
        opinions=OpinionSummary(),
        risk=risk,
        forecast=None,
    )

    assert result.forecast is None
    assert len(result.markdown) > 0
