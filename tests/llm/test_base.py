"""LLMClient base 類別測試."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ring_of_hands.llm.base import (
    CacheMetadata,
    ConfigValidationError,
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

    def test_system_block_cache_flag_is_advisory(self) -> None:
        """`cache=True` 由 SDK 後端消費; CLI 後端會忽略此欄位."""
        block = LLMSystemBlock(text="x", cache=True, label="persona")
        assert block.cache is True
        block2 = LLMSystemBlock(text="y", cache=False, label="rules")
        assert block2.cache is False

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

    def test_cache_metadata_defaults_zero(self) -> None:
        """非 Anthropic SDK 後端恆填 0; 預設值即為 0."""
        cm = CacheMetadata()
        assert cm.cache_read_input_tokens == 0
        assert cm.cache_creation_input_tokens == 0


class TestLLMCallFailedError:
    def test_stores_reason_and_cause(self) -> None:
        cause = RuntimeError("x")
        err = LLMCallFailedError(reason="timeout", cause=cause)
        assert err.reason == "timeout"
        assert err.cause is cause


class TestConfigValidationError:
    def test_is_exception(self) -> None:
        err = ConfigValidationError("claude CLI 不可執行")
        assert isinstance(err, Exception)
        assert "claude CLI 不可執行" in str(err)

    def test_reexported_from_project_agent_agent(self) -> None:
        """向後相容: project_agent.agent 仍可 import ConfigValidationError."""
        from ring_of_hands.project_agent.agent import (
            ConfigValidationError as PAConfigValidationError,
        )

        # 兩處 import 應為同一 class (不是 duplicated symbol).
        assert PAConfigValidationError is ConfigValidationError
