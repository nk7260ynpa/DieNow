"""Dispatch 主入口.

將 action 路由至對應規則模組; 負責:
- 在執行規則前進行 `check_dispatch_invariants` 檢查 (INV-3/4/7/8).
- 執行規則得到 `DispatchResult`.
- 若為 pov_6 自由 action, 登記 `register_free_action` 以維護 INV-7.
"""

from __future__ import annotations

from typing import Any, Callable

from ring_of_hands.rules_engine.button_rule import apply_press
from ring_of_hands.rules_engine.invariants import check_dispatch_invariants
from ring_of_hands.rules_engine.move_rule import apply_move
from ring_of_hands.rules_engine.ring_rule import apply_touch_ring
from ring_of_hands.rules_engine.speak_rule import (
    MAX_SPEAK_LENGTH_DEFAULT,
    RealtimeChatHook,
    apply_speak,
)
from ring_of_hands.world_model.engine import DispatchResult, WorldEngine
from ring_of_hands.world_model.types import (
    Action,
    Event,
    MoveAction,
    ObserveAction,
    PressAction,
    SpeakAction,
    TouchRingAction,
    WaitAction,
)


DispatchContext = dict[str, Any]
"""呼叫 dispatch 時的額外上下文:

- `is_free_agent`: bool (pov_6 自由 action 為 True)
- `expected_scripted_event`: dict | None (INV-3/8 比對用)
- `max_speak_length`: int (speak 的訊息長度上限)
- `realtime_chat_hook`: Callable | None (speak 的 hook)
"""


def dispatch(
    engine: WorldEngine,
    pov_id: int,
    action: Action,
    *,
    context: DispatchContext | None = None,
) -> DispatchResult:
    """將 action dispatch 至對應規則模組."""
    ctx = context or {}
    is_free_agent: bool = bool(ctx.get("is_free_agent", pov_id == 6))
    expected_scripted_event = ctx.get("expected_scripted_event")

    check_dispatch_invariants(
        engine,
        pov_id,
        action,
        is_free_agent=is_free_agent,
        expected_scripted_event=expected_scripted_event,
    )

    if is_free_agent:
        engine.register_free_action(pov_id)

    max_speak_length: int = int(ctx.get("max_speak_length", MAX_SPEAK_LENGTH_DEFAULT))
    realtime_chat_hook: RealtimeChatHook | None = ctx.get("realtime_chat_hook")

    result: DispatchResult
    if isinstance(action, MoveAction):
        result = apply_move(engine, pov_id, action)
    elif isinstance(action, PressAction):
        result = apply_press(engine, pov_id, action)
    elif isinstance(action, TouchRingAction):
        result = apply_touch_ring(engine, pov_id)
    elif isinstance(action, SpeakAction):
        result = apply_speak(
            engine,
            pov_id,
            action,
            max_length=max_speak_length,
            realtime_chat_hook=realtime_chat_hook,
        )
    elif isinstance(action, WaitAction):
        result = DispatchResult(state=engine.state, events=[])
    elif isinstance(action, ObserveAction):
        result = DispatchResult(state=engine.state, events=[])
    else:
        raise TypeError(f"未支援的 action 型別: {type(action).__name__}")

    return result


def install_default_dispatcher(
    engine: WorldEngine,
    *,
    max_speak_length: int = MAX_SPEAK_LENGTH_DEFAULT,
    realtime_chat_hook: RealtimeChatHook | None = None,
    context_provider: Callable[[int, Action], DispatchContext] | None = None,
) -> None:
    """將 dispatcher 注入 WorldEngine.

    Args:
        engine: WorldEngine.
        max_speak_length: 訊息長度上限.
        realtime_chat_hook: 即時對話 hook (來自 pov-manager).
        context_provider: callable, 每次 dispatch 前回傳 context dict; 用於
            pov-manager 傳入 scripted event 等.
    """

    def _wrapped(engine_: WorldEngine, pov_id: int, action: Action) -> DispatchResult:
        base_ctx: DispatchContext = {
            "max_speak_length": max_speak_length,
            "realtime_chat_hook": realtime_chat_hook,
        }
        if context_provider is not None:
            base_ctx.update(context_provider(pov_id, action))
        return dispatch(engine_, pov_id, action, context=base_ctx)

    engine.set_dispatcher(_wrapped)


__all__ = ["DispatchContext", "dispatch", "install_default_dispatcher"]
