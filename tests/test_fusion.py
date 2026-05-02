from __future__ import annotations

from app.data.fusion import DataFusionService
from app.schemas.doc import UnifiedDoc


def test_merge_and_dedup():
    service = DataFusionService()
    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", content="c1", url="http://a.com/1"),
        UnifiedDoc(doc_id="2", topic_id="t", source_type="platform", content="c2", url="http://a.com/1"),  # same url
        UnifiedDoc(doc_id="3", topic_id="t", source_type="news", content="c3", title="unique"),
    ]
    result = service.merge_and_dedup(docs)
    # doc_1 and doc_2 share the same url → one should be deduplicated
    assert len(result) == 2


def test_source_distribution():
    service = DataFusionService()
    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", content="c1"),
        UnifiedDoc(doc_id="2", topic_id="t", source_type="news", content="c2"),
        UnifiedDoc(doc_id="3", topic_id="t", source_type="platform", content="c3"),
    ]
    dist = service.source_distribution(docs)
    assert dist["news"] == 2
    assert dist["platform"] == 1


def test_empty_merge():
    service = DataFusionService()
    result = service.merge_and_dedup([])
    assert result == []
    assert service.source_distribution([]) == {}
