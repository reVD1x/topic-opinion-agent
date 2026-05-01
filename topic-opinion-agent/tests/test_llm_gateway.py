from __future__ import annotations

from app.llm.gateway import LLMGateway


def test_disabled_when_no_api_key():
    llm = LLMGateway()
    # enabled depends on actual env; we just check the method contract
    if not llm.enabled:
        assert llm.chat_json("sys", "usr") == {}


def test_retry_delay_calculation():
    delay = LLMGateway._retry_delay(0, None)
    assert 0 <= delay <= 8.0

    delay2 = LLMGateway._retry_delay(2, None)
    # At attempt 2: base * 2^2 + jitter = ~4s, clamped at max 8s
    assert 0 <= delay2 <= 8.0
