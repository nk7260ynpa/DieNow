"""LLM Client 抽象.

提供 `LLMClient` Protocol 與兩個實作:
- `AnthropicClient`: 以 `anthropic` SDK 實際呼叫 Claude API, 預設套用
  prompt caching (`cache_control={"type": "ephemeral"}`).
- `FakeAnthropicClient`: 測試期離線替身, 從 fixture 讀取預錄 response.
"""

from ring_of_hands.llm.base import (
    CacheMetadata,
    LLMCallFailedError,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMSystemBlock,
    LLMToolDefinition,
)
from ring_of_hands.llm.fake_client import FakeAnthropicClient, FakeClientFixture

__all__ = [
    "AnthropicClient",
    "CacheMetadata",
    "FakeAnthropicClient",
    "FakeClientFixture",
    "LLMCallFailedError",
    "LLMClient",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMSystemBlock",
    "LLMToolDefinition",
]


def __getattr__(name: str) -> object:
    """Lazy import `AnthropicClient` 以避免在無 anthropic SDK 的環境下 import 失敗."""
    if name == "AnthropicClient":
        from ring_of_hands.llm.anthropic_client import AnthropicClient

        return AnthropicClient
    raise AttributeError(name)
