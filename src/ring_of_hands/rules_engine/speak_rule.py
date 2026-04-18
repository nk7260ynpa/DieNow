"""說話規則.

對應 specs/rules-engine/spec.md "說話與即時對話".
"""

from __future__ import annotations

from typing import Callable

from ring_of_hands.world_model.engine import DispatchResult, WorldEngine
from ring_of_hands.world_model.types import (
    ActionRejectedEvent,
    Event,
    SpeakAction,
    SpeakEvent,
)


MAX_SPEAK_LENGTH_DEFAULT = 512


RealtimeChatHook = Callable[[int, SpeakAction], list[Event]]
"""pov-manager 可注入的 hook: `(speaker_pov_id, action) -> 額外 events`."""


def apply_speak(
    engine: WorldEngine,
    body_id: int,
    action: SpeakAction,
    *,
    max_length: int = MAX_SPEAK_LENGTH_DEFAULT,
    realtime_chat_hook: RealtimeChatHook | None = None,
) -> DispatchResult:
    """處理說話動作.

    Args:
        engine: WorldEngine.
        body_id: 發話者.
        action: `SpeakAction`.
        max_length: 訊息長度上限 (由 scenario config 傳入).
        realtime_chat_hook: 若 `targets` 含 k<6 的 pov 且 hook 存在,
            則呼叫 hook 以觸發即時對話; hook 必須負責寫入 SpeakEvent
            與可能的 ActionDowngradedEvent.

    Returns:
        `DispatchResult`.
    """
    tick = engine.state.tick
    body = engine.find_body(body_id)
    events: list[Event] = []

    if body.status != "alive":
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "body_not_alive"},
            )
        )
        return DispatchResult(state=engine.state, events=events)

    msg = action.msg
    if not msg:
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "empty_message"},
            )
        )
        return DispatchResult(state=engine.state, events=events)

    if len(msg) > max_length:
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "message_too_long", "length": len(msg)},
            )
        )
        return DispatchResult(state=engine.state, events=events)

    targets = list(action.targets)
    events.append(
        SpeakEvent(
            tick=tick,
            actor=body_id,
            payload={"msg": msg, "targets": targets},
        )
    )
    engine.append_public_speech(
        {"tick": tick, "actor": body_id, "msg": msg, "targets": targets}
    )

    # 若 pov_6 點名 pov_k<6 且 hook 存在, 透過 hook 觸發 pov-manager 的
    # 即時對話處理.
    if (
        realtime_chat_hook is not None
        and body_id == 6
        and any(1 <= t <= 5 for t in targets)
    ):
        extra = realtime_chat_hook(body_id, action)
        events.extend(extra)

    return DispatchResult(state=engine.state, events=events)


__all__ = ["apply_speak", "RealtimeChatHook", "MAX_SPEAK_LENGTH_DEFAULT"]
