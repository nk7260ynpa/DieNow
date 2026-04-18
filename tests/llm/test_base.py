"""LLMClient base 類別測試."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ring_of_hands.llm.base import (
    CacheMetadata,
    LLMCallFailedError,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMSystemBlock,
)


class TestLLMTypes:
    def test_system_block_frozen(self) -> None:
        block = LLMSystemBlock(text="persona")
        with pytest.raises(ValidationError):
            block.text = "other"  # type: ignore[misc]

    def test_message_role_enum(self) -> None:
        with pytest.raises(ValidationError):
            LLMMessage(role="system", content="x")  # type: ignore[arg-type]

    def test_llm_request_defaults(self) -> None:
        req = LLMRequest(
            model="claude-sonnet-4-7",
            system_blocks=(LLMSystemBlock(text="a"),),
            messages=(LLMMessage(role="user", content="hi"),),
        )
        assert req.timeout_seconds == 30.0
        assert req.temperature == 0.7

    def test_response_cache_metadata(self) -> None:
        cache = CacheMetadata(cache_read_input_tokens=123, cache_creation_input_tokens=0)
        resp = LLMResponse(text="ok", cache=cache)
        assert resp.cache.cache_read_input_tokens == 123


class TestLLMCallFailedError:
    def test_stores_reason_and_cause(self) -> None:
        cause = RuntimeError("x")
        err = LLMCallFailedError(reason="timeout", cause=cause)
        assert err.reason == "timeout"
        assert err.cause is cause
