"""按鈕按壓規則.

對應 specs/rules-engine/spec.md "按鈕按壓判定".
"""

from __future__ import annotations

from ring_of_hands.rules_engine.helpers import chebyshev_distance
from ring_of_hands.world_model.engine import DispatchResult, WorldEngine
from ring_of_hands.world_model.types import (
    ActionRejectedEvent,
    ButtonLitEvent,
    DeathEvent,
    Event,
    PressAction,
    PressEvent,
)


def apply_press(
    engine: WorldEngine, body_id: int, action: PressAction
) -> DispatchResult:
    """處理按鈕按壓動作.

    Args:
        engine: WorldEngine.
        body_id: 發起按壓的 body id.
        action: `PressAction`.

    Returns:
        `DispatchResult` 含本次產出的 event 清單與新 state.

    Scenario 覆蓋:
    - body 按下正確按鈕 → 亮燈
    - body 按下錯誤按鈕 → corpse
    - 距離過遠無法按壓
    """
    body = engine.find_body(body_id)
    button = engine.find_button(action.button_id)
    tick = engine.state.tick
    events: list[Event] = []

    # 記錄按壓意圖 (不論成功失敗) 作為 audit trail.
    events.append(
        PressEvent(
            tick=tick,
            actor=body_id,
            payload={"button_id": action.button_id},
        )
    )

    if body.status != "alive":
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "body_not_alive", "button_id": action.button_id},
            )
        )
        return DispatchResult(state=engine.state, events=events)

    # 鄰接檢查 (chebyshev_distance <= 1, 允許重合).
    if chebyshev_distance(body.position, button.position) > 1:
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={
                    "reason": "out_of_range",
                    "button_id": action.button_id,
                    "distance": chebyshev_distance(body.position, button.position),
                },
            )
        )
        return DispatchResult(state=engine.state, events=events)

    if body_id == action.button_id:
        # 按對 → 亮燈 (若尚未亮).
        if not button.lit:
            engine.update_button(action.button_id, lit=True)
            events.append(
                ButtonLitEvent(
                    tick=tick,
                    actor=body_id,
                    payload={"button_id": action.button_id},
                )
            )
        return DispatchResult(state=engine.state, events=events)

    # 按錯 → 死亡.
    engine.update_body(body_id, status="corpse", hp=0)
    events.append(
        DeathEvent(
            tick=tick,
            actor=body_id,
            payload={
                "cause": "press_wrong",
                "attempted_button_id": action.button_id,
            },
        )
    )
    return DispatchResult(state=engine.state, events=events)


__all__ = ["apply_press"]
