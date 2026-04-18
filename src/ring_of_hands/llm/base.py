"""LLM Client 介面與資料結構.

`LLMClient` 為 Protocol; 所有 LLM 呼叫端 MUST 僅依賴此 Protocol 以支援
離線測試 (FakeAnthropicClient).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMSystemBlock(BaseModel):
    """可快取的 system block."""

    model_config = ConfigDict(frozen=True)

    text: str
    cache: bool = True
    label: str | None = None
    """人類可讀標籤 (例如 'persona', 'rules', 'prior_life')."""


class LLMMessage(BaseModel):
    """user/assistant 訊息."""

    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    content: str


class LLMToolDefinition(BaseModel):
    """Anthropic tool use 定義."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any]


class LLMRequest(BaseModel):
    """送往 LLM 的請求."""

    model_config = ConfigDict(frozen=True)

    model: str
    system_blocks: tuple[LLMSystemBlock, ...]
    messages: tuple[LLMMessage, ...]
    max_tokens: int = 1024
    tools: tuple[LLMToolDefinition, ...] = ()
    tool_choice: dict[str, Any] | None = None
    temperature: float = 0.7
    timeout_seconds: float = 30.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CacheMetadata(BaseModel):
    """Prompt caching 指標."""

    model_config = ConfigDict(frozen=True)

    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class LLMResponse(BaseModel):
    """LLM 回應."""

    model_config = ConfigDict(frozen=True)

    text: str
    tool_use: dict[str, Any] | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    cache: CacheMetadata = Field(default_factory=CacheMetadata)
    raw: dict[str, Any] = Field(default_factory=dict)


class LLMCallFailedError(Exception):
    """LLM 呼叫失敗 (timeout / network / parse)."""

    def __init__(self, reason: str, cause: Exception | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


class LLMClient(Protocol):
    """LLM 呼叫介面.

    實作 class MUST 接受 `LLMRequest` 並回傳 `LLMResponse`, 或於呼叫失敗時
    raise `LLMCallFailedError`.
    """

    def call(self, request: LLMRequest) -> LLMResponse:
        """執行 LLM 呼叫."""
        ...


__all__ = [
    "CacheMetadata",
    "LLMCallFailedError",
    "LLMClient",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMSystemBlock",
    "LLMToolDefinition",
]
