"""Project Agent 的 action 解析器.

輸入為 LLM 回傳的 structured output (tool_use.input 或 JSON 字串), 輸出
為 Pydantic `Action` 子型別.
"""

from __future__ import annotations

import json
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
    # 轉換 Pydantic model.
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


def parse_action_from_response(response: LLMResponse) -> Action:
    """從 `LLMResponse` 萃取 action.

    優先讀取 `tool_use.input`, 否則嘗試將 `text` 當 JSON 解析.
    """
    if response.tool_use is not None:
        payload = response.tool_use.get("input")
        if not isinstance(payload, dict):
            raise ActionParseError(
                "tool_use.input 必須為 dict", raw_response=response
            )
        return parse_action(payload)
    # fallback: 解析 text JSON.
    text = (response.text or "").strip()
    if not text:
        raise ActionParseError("LLM 回應為空", raw_response=response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ActionParseError(
            f"text 非合法 JSON: {exc}", raw_response=response
        ) from exc
    return parse_action(payload)


__all__ = [
    "ActionParseError",
    "parse_action",
    "parse_action_from_response",
]
