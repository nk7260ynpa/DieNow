"""AnthropicClient 測試.

為避免真實 API 呼叫, 本測試以 monkeypatch 替換底層 `anthropic.Anthropic`
client 的 `messages.create` 方法.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ring_of_hands.llm.base import (
    LLMCallFailedError,
    LLMMessage,
    LLMRequest,
    LLMSystemBlock,
)


@pytest.fixture
def patched_anthropic(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch anthropic.Anthropic 以避免真實網路呼叫."""
    from ring_of_hands.llm import anthropic_client as mod

    if not mod._ANTHROPIC_AVAILABLE:  # pragma: no cover
        pytest.skip("anthropic SDK 未安裝")

    captured: dict[str, Any] = {"kwargs": None}

    class FakeMessages:
        def __init__(self) -> None:
            self.usage = SimpleNamespace(
                input_tokens=1000,
                output_tokens=50,
                cache_read_input_tokens=800,
                cache_creation_input_tokens=200,
            )

        def create(self, **kwargs: Any) -> Any:
            captured["kwargs"] = kwargs
            # 回傳具 content/usage 的假 message.
            content = [SimpleNamespace(type="text", text="hello")]
            return SimpleNamespace(content=content, usage=self.usage)

    class FakeAnthropic:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key
            self.messages = FakeMessages()

    monkeypatch.setattr(mod, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))
    monkeypatch.setattr(mod, "_ANTHROPIC_AVAILABLE", True)
    return captured


class TestAnthropicClient:
    def test_requires_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from ring_of_hands.llm.anthropic_client import AnthropicClient

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError):
            AnthropicClient()

    def test_call_passes_system_array_with_cache_control(
        self, patched_anthropic: dict[str, Any]
    ) -> None:
        from ring_of_hands.llm.anthropic_client import AnthropicClient

        client = AnthropicClient(api_key="test-key")
        req = LLMRequest(
            model="claude-sonnet-4-7",
            system_blocks=(
                LLMSystemBlock(text="persona", cache=True),
                LLMSystemBlock(text="rules", cache=True),
                LLMSystemBlock(text="prior", cache=True),
            ),
            messages=(LLMMessage(role="user", content="go"),),
        )
        resp = client.call(req)
        assert resp.text == "hello"
        kwargs = patched_anthropic["kwargs"]
        assert kwargs is not None
        sys_arr = kwargs["system"]
        assert len(sys_arr) == 3
        for item in sys_arr:
            assert item["type"] == "text"
            assert item["cache_control"] == {"type": "ephemeral"}

    def test_user_message_has_no_cache_control(
        self, patched_anthropic: dict[str, Any]
    ) -> None:
        from ring_of_hands.llm.anthropic_client import AnthropicClient

        client = AnthropicClient(api_key="test-key")
        req = LLMRequest(
            model="claude-sonnet-4-7",
            system_blocks=(LLMSystemBlock(text="persona"),),
            messages=(LLMMessage(role="user", content="go"),),
        )
        client.call(req)
        kwargs = patched_anthropic["kwargs"]
        for msg in kwargs["messages"]:
            # Anthropic SDK 允許 content 為字串或 list; 本實作以字串送出.
            assert isinstance(msg["content"], str)
            assert "cache_control" not in msg

    def test_cache_usage_populated(self, patched_anthropic: dict[str, Any]) -> None:
        from ring_of_hands.llm.anthropic_client import AnthropicClient

        client = AnthropicClient(api_key="test-key")
        req = LLMRequest(
            model="claude-sonnet-4-7",
            system_blocks=(LLMSystemBlock(text="persona"),),
            messages=(LLMMessage(role="user", content="hi"),),
        )
        resp = client.call(req)
        assert resp.cache.cache_read_input_tokens == 800
        assert resp.cache.cache_creation_input_tokens == 200

    def test_timeout_retries_then_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ring_of_hands.llm import anthropic_client as mod

        class _Timeout(Exception):
            pass

        # 模擬 APITimeoutError 與 messages.create 一律 timeout.
        class FakeMessages:
            def create(self, **_: Any) -> Any:
                raise _Timeout("timeout")

        class FakeAnthropic:
            def __init__(self, *, api_key: str) -> None:
                self.messages = FakeMessages()

        monkeypatch.setattr(
            mod,
            "anthropic",
            SimpleNamespace(Anthropic=FakeAnthropic),
        )
        monkeypatch.setattr(mod, "APITimeoutError", _Timeout)
        monkeypatch.setattr(mod, "_ANTHROPIC_AVAILABLE", True)
        # 讓 time.sleep 不要真的等.
        monkeypatch.setattr(mod.time, "sleep", lambda _: None)

        client = mod.AnthropicClient(
            api_key="test",
            max_retries=1,
            retry_backoff_seconds=0,
        )
        with pytest.raises(LLMCallFailedError):
            client.call(
                LLMRequest(
                    model="m",
                    system_blocks=(LLMSystemBlock(text="x"),),
                    messages=(LLMMessage(role="user", content="go"),),
                )
            )
