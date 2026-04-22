"""LLM Client 介面與資料結構.

`LLMClient` 為 Protocol; 所有 LLM 呼叫端 MUST 僅依賴此 Protocol 以支援
離線測試 (FakeLLMClient).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMSystemBlock(BaseModel):
    """可快取的 system block.

    Attributes:
        text: block 的文字內容.
        cache: 歷史語意為「建議套用 prompt caching」; `ClaudeCLIClient` 會
            忽略此欄位. 於本 change (migrate-to-claude-cli-subprocess) 之後
            已無 SDK 後端消費此欄位, 保留為相容欄位, 方便日後上游恢復
            caching 能力時重新啟用.
        label: 人類可讀標籤 (例如 'persona', 'rules', 'prior_life').
    """

    model_config = ConfigDict(frozen=True)

    text: str
    cache: bool = True
    label: str | None = None


class LLMMessage(BaseModel):
    """user/assistant 訊息."""

    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    content: str


class LLMToolDefinition(BaseModel):
    """Anthropic tool use 定義 (僅 SDK 後端使用).

    `ClaudeCLIClient` 不支援 tool use, 收到此欄位會被忽略; 保留為向後相容
    欄位.
    """

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
    timeout_seconds: float = 180.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CacheMetadata(BaseModel):
    """Prompt caching 指標.

    欄位保留以維持下游 log schema 穩定; 非 Anthropic SDK 後端 (例如
    `ClaudeCLIClient`) 會將兩個欄位恆填 0.
    """

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


class ConfigValidationError(Exception):
    """LLM 相關設定不合法 (缺 CLI / API key / 模型名非支援等).

    於本專案由 `ClaudeCLIClient.__init__`、`scenario_runner.config_loader`、
    `project_agent.validate_model_name` 等處 raise. 歷史上此例外位於
    `ring_of_hands.project_agent.agent`, 本 change 遷移至 `llm.base` 以
    解除循環 import; `project_agent.agent` 仍 re-export 以保持向後相容.
    """


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
    "ConfigValidationError",
    "LLMCallFailedError",
    "LLMClient",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMSystemBlock",
    "LLMToolDefinition",
]
