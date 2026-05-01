from __future__ import annotations

from unittest.mock import MagicMock

from app.agents.preprocess_agent import PreprocessAgent
from app.schemas.doc import UnifiedDoc


def test_removes_empty_docs():
    agent = PreprocessAgent()
    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", content="   "),
        UnifiedDoc(doc_id="2", topic_id="t", source_type="news", content="valid"),
    ]
    result = agent.run(docs)
    assert len(result) == 1
    assert result[0].doc_id == "2"


def test_dedup_by_title_and_first_chars():
    agent = PreprocessAgent()
    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", title="标题A", content="相同内容开头"),
        UnifiedDoc(doc_id="2", topic_id="t", source_type="platform", title="标题A", content="相同内容开头"),
    ]
    result = agent.run(docs)
    assert len(result) == 1


def test_truncate_long_content():
    agent = PreprocessAgent()
    long_content = "x" * 3000
    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", content=long_content),
    ]
    result = agent.run(docs)
    assert len(result) == 1
    assert len(result[0].content) == 2000  # CONTENT_TRUNCATE_LEN


def test_topic_relevance_filter():
    """LLM returns relevant_ids for only 2 of 4 docs."""
    agent = PreprocessAgent()
    mock_llm = MagicMock()
    mock_llm.enabled = True
    mock_llm.chat_json.return_value = {"relevant_ids": [0, 3]}

    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", title="关于日本经济", content="日本GDP数据"),
        UnifiedDoc(doc_id="2", topic_id="t", source_type="platform", title="三星存储降价", content="DDR5内存崩盘"),
        UnifiedDoc(doc_id="3", topic_id="t", source_type="platform", title="小米15 Ultra", content="夜景拍照天花板"),
        UnifiedDoc(doc_id="4", topic_id="t", source_type="tavily", title="日本文化", content="日本传统文化介绍"),
    ]
    result = agent.run(docs, topic_id="日本", llm=mock_llm)
    assert len(result) == 2
    assert {r.doc_id for r in result} == {"1", "4"}


def test_topic_relevance_skip_when_llm_disabled():
    """When LLM is disabled, no filtering happens."""
    agent = PreprocessAgent()
    mock_llm = MagicMock()
    mock_llm.enabled = False

    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", title="无关", content="内容"),
        UnifiedDoc(doc_id="2", topic_id="t", source_type="platform", title="无关2", content="内容2"),
    ]
    result = agent.run(docs, topic_id="日本", llm=mock_llm)
    mock_llm.chat_json.assert_not_called()
    assert len(result) == 2


def test_topic_relevance_no_topic_id():
    """Without topic_id, no filtering happens."""
    agent = PreprocessAgent()
    docs = [
        UnifiedDoc(doc_id="1", topic_id="t", source_type="news", title="无关", content="内容"),
    ]
    result = agent.run(docs)  # no topic_id, no llm
    assert len(result) == 1
