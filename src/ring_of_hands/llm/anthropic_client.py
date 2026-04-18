"""Anthropic SDK 的 LLMClient 實作.

套用 prompt caching: 將每個 `LLMSystemBlock` 轉為 Anthropic system array
的 element, 對於 `cache=True` 的 block 附加 `cache_control={"type": "ephemeral"}`.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

try:  # pragma: no cover - import 失敗時交由呼叫端處理.
    import anthropic
    from anthropic import APIConnectionError, APIStatusError, APITimeoutError

    _ANTHROPIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]
    APIConnectionError = APIStatusError = APITimeoutError = Exception  # type: ignore[misc]
    _ANTHROPIC_AVAILABLE = False

from ring_of_hands.llm.base import (
    CacheMetadata,
    LLMCallFailedError,
    LLMRequest,
    LLMResponse,
)


logger = logging.getLogger(__name__)


class AnthropicClient:
    """以 Anthropic SDK 呼叫 Claude 模型.

    Args:
        api_key: Anthropic API key; 若為 `None` 會讀 `ANTHROPIC_API_KEY`.
        max_retries: 暫時性錯誤的重試次數. 預設 2 (即共嘗試 3 次).
        retry_backoff_seconds: 指數退避的基礎秒數.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        if not _ANTHROPIC_AVAILABLE:  # pragma: no cover
            raise RuntimeError("anthropic SDK 未安裝; 請在 pyproject.toml 列為依賴.")
        resolved_api_key = api_key if api_key is not None else os.getenv(
            "ANTHROPIC_API_KEY"
        )
        if not resolved_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self._client = anthropic.Anthropic(api_key=resolved_api_key)
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def call(self, request: LLMRequest) -> LLMResponse:
        """執行呼叫.

        Returns:
            `LLMResponse`.

        Raises:
            LLMCallFailedError: 超過重試上限或遇到不可重試錯誤.
        """
        system_arr = _build_system_array(request)
        messages = [m.model_dump() for m in request.messages]
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": system_arr,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.tools:
            kwargs["tools"] = [tool.model_dump() for tool in request.tools]
        if request.tool_choice is not None:
            kwargs["tool_choice"] = request.tool_choice

        last_error: Exception | None = None
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            try:
                response = self._client.messages.create(
                    timeout=request.timeout_seconds,
                    **kwargs,
                )
                return _build_response(response)
            except APITimeoutError as exc:
                last_error = exc
                logger.warning(
                    "Anthropic 呼叫 timeout (attempt %d/%d): %s",
                    attempt + 1,
                    attempts,
                    exc,
                )
            except APIConnectionError as exc:
                last_error = exc
                logger.warning(
                    "Anthropic 連線錯誤 (attempt %d/%d): %s",
                    attempt + 1,
                    attempts,
                    exc,
                )
            except APIStatusError as exc:
                # 僅在 5xx 重試, 4xx 視為不可重試.
                if 500 <= getattr(exc, "status_code", 0) < 600:
                    last_error = exc
                    logger.warning(
                        "Anthropic 5xx (attempt %d/%d): %s",
                        attempt + 1,
                        attempts,
                        exc,
                    )
                else:
                    raise LLMCallFailedError(
                        reason=f"anthropic_api_status_{getattr(exc, 'status_code', 0)}",
                        cause=exc,
                    ) from exc
            except Exception as exc:  # noqa: BLE001
                raise LLMCallFailedError(
                    reason="anthropic_unknown",
                    cause=exc,
                ) from exc

            if attempt < attempts - 1:
                time.sleep(self._retry_backoff_seconds * (2**attempt))

        raise LLMCallFailedError(
            reason="anthropic_retry_exhausted",
            cause=last_error,
        )


def _build_system_array(request: LLMRequest) -> list[dict[str, Any]]:
    """將 LLMRequest.system_blocks 轉為 Anthropic system array."""
    blocks: list[dict[str, Any]] = []
    for block in request.system_blocks:
        item: dict[str, Any] = {"type": "text", "text": block.text}
        if block.cache:
            item["cache_control"] = {"type": "ephemeral"}
        blocks.append(item)
    return blocks


def _build_response(raw: Any) -> LLMResponse:
    """將 Anthropic SDK 的 Message object 轉為 LLMResponse."""
    # content 為 list; 尋找 text block 與 tool_use block.
    text_parts: list[str] = []
    tool_use: dict[str, Any] | None = None
    for block in getattr(raw, "content", []):
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(getattr(block, "text", ""))
        elif block_type == "tool_use":
            tool_use = {
                "name": getattr(block, "name", None),
                "input": getattr(block, "input", {}),
                "id": getattr(block, "id", None),
            }
    usage_obj = getattr(raw, "usage", None)
    usage_dict: dict[str, int] = {}
    cache_read = 0
    cache_creation = 0
    if usage_obj is not None:
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            val = getattr(usage_obj, field, None)
            if val is not None:
                usage_dict[field] = int(val)
        cache_read = usage_dict.get("cache_read_input_tokens", 0)
        cache_creation = usage_dict.get("cache_creation_input_tokens", 0)
    return LLMResponse(
        text="\n".join(text_parts),
        tool_use=tool_use,
        usage=usage_dict,
        cache=CacheMetadata(
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        ),
        raw={},
    )


__all__ = ["AnthropicClient"]
