"""移動與碰撞規則.

對應 specs/rules-engine/spec.md "移動與碰撞".
"""

from __future__ import annotations

from ring_of_hands.rules_engine.helpers import in_bounds
from ring_of_hands.world_model.engine import DispatchResult, WorldEngine
from ring_of_hands.world_model.types import (
    ActionRejectedEvent,
    Event,
    MoveAction,
    MoveEvent,
)

LEGAL_DELTAS: frozenset[tuple[int, int]] = frozenset(
    {
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (0, 0),
    }
)


def apply_move(
    engine: WorldEngine, body_id: int, action: MoveAction
) -> DispatchResult:
    """處理移動動作."""
    state = engine.state
    tick = state.tick
    body = engine.find_body(body_id)
    events: list[Event] = []
    delta = tuple(action.delta)

    if body.status != "alive":
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "body_not_alive"},
            )
        )
        return DispatchResult(state=state, events=events)

    if delta not in LEGAL_DELTAS:
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "illegal_delta", "delta": list(delta)},
            )
        )
        return DispatchResult(state=state, events=events)

    target = (body.position[0] + delta[0], body.position[1] + delta[1])

    if not in_bounds(target, state.room_size):
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "out_of_bounds", "target": list(target)},
            )
        )
        return DispatchResult(state=state, events=events)

    # 碰撞檢查: 其他 body / 按鈕 / 戒指佔用位置.
    for other in state.bodies:
        if other.body_id == body_id:
            continue
        if other.position == target:
            events.append(
                ActionRejectedEvent(
                    tick=tick,
                    actor=body_id,
                    payload={
                        "reason": "collision",
                        "target": list(target),
                        "collided_with_body": other.body_id,
                    },
                )
            )
            return DispatchResult(state=state, events=events)

    # 按鈕與戒指亦佔空間, 但允許進入「鄰接」; 按鈕格本身禁止走上去,
    # 除非 delta == (0, 0) 代表原地不動.
    if delta != (0, 0):
        for button in state.buttons:
            if button.position == target:
                events.append(
                    ActionRejectedEvent(
                        tick=tick,
                        actor=body_id,
                        payload={
                            "reason": "collision",
                            "target": list(target),
                            "collided_with_button": button.button_id,
                        },
                    )
                )
                return DispatchResult(state=state, events=events)
        if state.ring.position == target:
            # 允許踩在 ring 上, 這是接近 ring 的必要步驟.
            pass

    previous = body.position
    engine.update_body(body_id, position=target)
    events.append(
        MoveEvent(
            tick=tick,
            actor=body_id,
            payload={"from": list(previous), "to": list(target)},
        )
    )
    return DispatchResult(state=engine.state, events=events)


__all__ = ["apply_move"]
