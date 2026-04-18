"""Project Agent 的 action 解析器.

輸入為 LLM 回傳的 `LLMResponse`; 優先從 `response.text` 做 `json.loads`
(自動去除 Markdown code fence), 解析為 Pydantic `Action` 子型別.
`tool_use` 路徑保留為 fallback 以與舊 fixture 相容, 但會觸發
`DeprecationWarning`.

對應 change `migrate-to-claude-cli-subprocess` 的 D-4' 決策.
"""

from __future__ import annotations

import json
import re
import warnings
from typing import Any

from pydantic import ValidationError

from ring_of_hands.llm.base import LLMResponse
from ring_of_hands.world_model.types import (
    Action,
    MoveAction,
    ObserveAction,
    PressAction,
    SpeakAction,
    TouchRingAction,
    WaitAction,
)


class ActionParseError(Exception):
    """LLM 回應無法解析為合法 Action."""

    def __init__(self, reason: str, *, raw_response: Any = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw_response = raw_response


_ACTION_TYPE_MAP: dict[str, type[Action]] = {
    "move": MoveAction,
    "press": PressAction,
    "touch_ring": TouchRingAction,
    "speak": SpeakAction,
    "wait": WaitAction,
    "observe": ObserveAction,
}


# Markdown code fence (```json ... ``` or ``` ... ```).
_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json|JSON)?\s*(?P<body>.*?)\s*```",
    re.DOTALL,
)


def parse_action(payload: dict[str, Any]) -> Action:
    """將 dict 轉為合法 Action.

    Raises:
        ActionParseError: 若 `action` 欄位缺失 / 未支援 / 必要欄位驗證失敗.
    """
    if not isinstance(payload, dict):
        raise ActionParseError(
            "action payload 必須為 dict", raw_response=payload
        )
    action_type = payload.get("action")
    if action_type is None:
        raise ActionParseError(
            "缺少 action 欄位", raw_response=payload
        )
    action_cls = _ACTION_TYPE_MAP.get(action_type)
    if action_cls is None:
        raise ActionParseError(
            f"unknown_action_type: {action_type}", raw_response=payload
        )
    data = dict(payload)
    # SpeakAction.targets 若為 list → tuple.
    if action_type == "speak" and "targets" in data:
        targets = data["targets"]
        if isinstance(targets, list):
            data["targets"] = tuple(int(t) for t in targets)
    if action_type == "move" and "delta" in data:
        delta = data["delta"]
        if isinstance(delta, list):
            data["delta"] = (int(delta[0]), int(delta[1]))
    try:
        return action_cls.model_validate(data)
    except ValidationError as exc:
        raise ActionParseError(
            f"validation_error: {exc}", raw_response=payload
        ) from exc


def _strip_code_fence(text: str) -> str:
    """若 text 被 Markdown code fence 包住則去除; 否則原樣回傳."""
    stripped = text.strip()
    match = _CODE_FENCE_PATTERN.search(stripped)
    if match:
        return match.group("body").strip()
    return stripped


def parse_action_from_response(response: LLMResponse) -> Action:
    """從 `LLMResponse` 萃取 action.

    優先從 `response.text` 做 `json.loads` (自動去除 Markdown code fence);
    `tool_use` 路徑保留為 fallback, 命中時會印出 `DeprecationWarning`.

    Raises:
        ActionParseError: text 為空 / 非合法 JSON / schema 驗證失敗.
    """
    text = (response.text or "").strip()
    if text:
        cleaned = _strip_code_fence(text)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            # 若有 tool_use fallback 則嘗試; 否則 raise.
            if response.tool_use is not None:
                return _parse_from_tool_use(response.tool_use, response)
            raise ActionParseError(
                f"text 非合法 JSON: {exc}", raw_response=response
            ) from exc
        return parse_action(payload)

    # text 為空, 嘗試 tool_use fallback.
    if response.tool_use is not None:
        return _parse_from_tool_use(response.tool_use, response)

    raise ActionParseError("LLM 回應為空", raw_response=response)


def _parse_from_tool_use(
    tool_use: dict[str, Any], response: LLMResponse
) -> Action:
    """從 `tool_use.input` 解析 action (僅為向後相容路徑)."""
    warnings.warn(
        (
            "action_parser 偵測到 LLMResponse.tool_use 欄位; 此路徑為向後"
            "相容 fallback, 將於未來 change 移除. 請確保 fixture 以 "
            "response.text JSON 字串承載 action."
        ),
        DeprecationWarning,
        stacklevel=3,
    )
    payload = tool_use.get("input")
    if not isinstance(payload, dict):
        raise ActionParseError(
            "tool_use.input 必須為 dict", raw_response=response
        )
    return parse_action(payload)


__all__ = [
    "ActionParseError",
    "parse_action",
    "parse_action_from_response",
]
