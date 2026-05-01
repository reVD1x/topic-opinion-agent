from __future__ import annotations

from app.schemas.analysis import OpinionPoint, OpinionSummary, RiskResult, SentimentItem
from app.workflow.pipeline import _verify_evidence_chain


def test_orphan_sentiment_detected():
    docs = [
        __import__("app.schemas.doc", fromlist=["UnifiedDoc"]).UnifiedDoc(
            doc_id="1", topic_id="t", source_type="news", content="test",
        )
    ]
    sentiments = [
        SentimentItem(doc_id="orphan", label="neutral", confidence=0.5),
    ]
    warnings = _verify_evidence_chain(docs, sentiments=sentiments)
    assert len(warnings) == 1
    assert "无法回溯" in warnings[0]


def test_valid_ids_not_warned():
    from app.schemas.doc import UnifiedDoc

    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", content="test"),
        UnifiedDoc(doc_id="2", topic_id="t", source_type="news", content="test"),
    ]
    sentiments = [
        SentimentItem(doc_id="1", label="positive", confidence=0.8),
        SentimentItem(doc_id="2", label="negative", confidence=0.7),
    ]
    warnings = _verify_evidence_chain(docs, sentiments=sentiments)
    assert len(warnings) == 0


def test_invalid_opinion_evidence_ids_removed():
    from app.schemas.doc import UnifiedDoc

    docs = [UnifiedDoc(doc_id="real", topic_id="t", source_type="news", content="test")]
    opinions = OpinionSummary(
        supports=[
            OpinionPoint(content="test", evidence_ids=["real", "fake"]),
        ],
    )
    warnings = _verify_evidence_chain(docs, opinions=opinions)
    assert len(warnings) == 1
    assert "已移除" in warnings[0]
    # In-place fix: fake id should be gone
    assert opinions.supports[0].evidence_ids == ["real"]


def test_invalid_risk_evidence_ids_removed():
    from app.schemas.doc import UnifiedDoc

    docs = [UnifiedDoc(doc_id="real", topic_id="t", source_type="news", content="test")]
    risk = RiskResult(risk_level="low", triggers=[], evidence_ids=["real", "ghost"])
    warnings = _verify_evidence_chain(docs, risk=risk)
    assert len(warnings) == 1
    assert "已移除" in warnings[0]
    assert risk.evidence_ids == ["real"]


def test_all_valid_no_warnings():
    from app.schemas.doc import UnifiedDoc

    docs = [
        UnifiedDoc(doc_id="a", topic_id="t", source_type="news", content="x"),
        UnifiedDoc(doc_id="b", topic_id="t", source_type="news", content="y"),
    ]
    sentiments = [SentimentItem(doc_id="a", label="neutral", confidence=0.5)]
    opinions = OpinionSummary(
        supports=[OpinionPoint(content="ok", evidence_ids=["a", "b"])],
    )
    risk = RiskResult(risk_level="low", triggers=[], evidence_ids=["a"])
    warnings = _verify_evidence_chain(
        docs, sentiments=sentiments, opinions=opinions, risk=risk,
    )
    assert len(warnings) == 0
