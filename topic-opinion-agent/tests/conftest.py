from __future__ import annotations

import pytest

from app.llm.gateway import LLMGateway
from app.schemas.doc import UnifiedDoc


@pytest.fixture
def mock_llm() -> LLMGateway:
    """Return an LLMGateway with LLM disabled to trigger all fallback paths."""
    llm = LLMGateway()
    llm.enabled = False
    return llm


@pytest.fixture
def sample_docs() -> list[UnifiedDoc]:
    """Return 5 constructed UnifiedDocs for testing."""
    return [
        UnifiedDoc(
            doc_id="doc_1",
            topic_id="test_topic",
            source_type="news",
            source_name="source_a",
            title="谣言四起：某品牌涉嫌违法操作",
            content="近日有传言称某品牌存在违法操作，涉及维权事件，引发公众关注。事故造成多人伤亡。",
        ),
        UnifiedDoc(
            doc_id="doc_2",
            topic_id="test_topic",
            source_type="platform",
            source_name="source_b",
            title="正面评价：新品发布会圆满成功",
            content="产品发布获得广泛好评，消费者反馈积极，销量远超预期。",
        ),
        UnifiedDoc(
            doc_id="doc_3",
            topic_id="test_topic",
            source_type="news",
            source_name="source_a",
            title="中立的行业分析报告",
            content="行业报告指出该品牌市场份额持平，既无重大利好也无显著风险，态势平稳。",
        ),
        UnifiedDoc(
            doc_id="doc_4",
            topic_id="test_topic",
            source_type="platform",
            source_name="source_c",
            title="用户投诉产品质量问题",
            content="多位用户投诉产品质量问题，反映售后维权困难，抵制该品牌的呼声渐起。",
        ),
        UnifiedDoc(
            doc_id="doc_5",
            topic_id="test_topic",
            source_type="news",
            source_name="source_b",
            title="重复内容文档",
            content="产品发布获得广泛好评，消费者反馈积极，销量远超预期。",
        ),
    ]
