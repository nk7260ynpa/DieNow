"""LLM Client 抽象.

提供 `LLMClient` Protocol 與兩個實作:
- `ClaudeCLIClient`: 以 Claude Code CLI subprocess (`claude -p ... --output-format
  stream-json`) 呼叫模型. 使用主機 `~/.claude/` 的 OAuth session, 適用於
  Claude Max 訂閱計費.
- `FakeLLMClient`: 測試期離線替身, 從 fixture 讀取預錄 response; 亦以
  `FakeAnthropicClient` 作為向後相容 alias.

本模組**不再**匯出 `AnthropicClient`; 該實作已於 change
`migrate-to-claude-cli-subprocess` 中移除, 以改走 Claude Max 訂閱認證.
"""

from ring_of_hands.llm.base import (
    CacheMetadata,
    ConfigValidationError,
    LLMCallFailedError,
    LLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMSystemBlock,
    LLMToolDefinition,
)
from ring_of_hands.llm.claude_cli_client import ClaudeCLIClient
from ring_of_hands.llm.fake_client import (
    FakeAnthropicClient,
    FakeClientFixture,
    FakeLLMClient,
)

__all__ = [
    "CacheMetadata",
    "ClaudeCLIClient",
    "ConfigValidationError",
    "FakeAnthropicClient",
    "FakeClientFixture",
    "FakeLLMClient",
    "LLMCallFailedError",
    "LLMClient",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMSystemBlock",
    "LLMToolDefinition",
]
