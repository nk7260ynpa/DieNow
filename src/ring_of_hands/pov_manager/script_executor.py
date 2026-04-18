"""劇本執行器.

本模組為 `tasks.md` 6.2 指定的檔案; 邏輯實作於 `manager.PovManager.
tick_scripted_povs`, 此檔僅提供獨立的 helper function 與 tasks.md 要求
的檔案入口.
"""

from __future__ import annotations

from typing import Any

from ring_of_hands.world_model.types import (
    Action,
    MoveAction,
    ObserveAction,
    PressAction,
    SpeakAction,
    TouchRingAction,
    WaitAction,
)


def action_from_scripted_event(event: dict[str, Any]) -> Action:
    """將 script event dict 轉為 Action (供 PovManager 使用).

    Args:
        event: 含 `action_type` / `payload` / `targets` 的 dict.

    Returns:
        對應的 Action 子型別.

    Raises:
        ValueError: 若 action_type 不受支援.
    """
    action_type = event["action_type"]
    payload = event.get("payload", {}) or {}
    targets = event.get("targets", []) or []
    if action_type == "move":
        delta = payload.get("delta", [0, 0])
        return MoveAction(delta=(int(delta[0]), int(delta[1])))
    if action_type == "press":
        return PressAction(button_id=int(payload.get("button_id")))
    if action_type == "touch_ring":
        return TouchRingAction()
    if action_type == "speak":
        return SpeakAction(
            msg=str(payload.get("msg", "")),
            targets=tuple(int(t) for t in targets),
        )
    if action_type == "wait":
        return WaitAction()
    if action_type == "observe":
        return ObserveAction()
    raise ValueError(f"無法轉為 Action 的 scripted action_type: {action_type}")


__all__ = ["action_from_scripted_event"]
