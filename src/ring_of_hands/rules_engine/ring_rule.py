"""戒指觸碰規則.

對應 specs/rules-engine/spec.md "戒指觸碰判定".
"""

from __future__ import annotations

from ring_of_hands.rules_engine.helpers import chebyshev_distance
from ring_of_hands.world_model.engine import DispatchResult, WorldEngine
from ring_of_hands.world_model.types import (
    ActionRejectedEvent,
    DeathEvent,
    Event,
    Outcome,
    OutcomeEvent,
)


def apply_touch_ring(engine: WorldEngine, body_id: int) -> DispatchResult:
    """處理觸碰戒指動作.

    Args:
        engine: WorldEngine.
        body_id: 發起觸碰的 body id.

    Returns:
        `DispatchResult`; 若成功觸碰戒指會填入 `outcome`.
    """
    state = engine.state
    tick = state.tick
    ring = state.ring
    body = engine.find_body(body_id)
    events: list[Event] = []

    # 前置條件 1: 防護窗已開且 ring 可觸碰.
    if not (state.shield_open and ring.touchable):
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "ring_not_ready"},
            )
        )
        return DispatchResult(state=state, events=events)

    if body.status != "alive":
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "body_not_alive"},
            )
        )
        return DispatchResult(state=state, events=events)

    # 前置條件 2: 鄰接戒指.
    if chebyshev_distance(body.position, ring.position) > 1:
        events.append(
            ActionRejectedEvent(
                tick=tick,
                actor=body_id,
                payload={"reason": "out_of_range"},
            )
        )
        return DispatchResult(state=state, events=events)

    # 判定勝負.
    if body_id == 6:
        engine.update_ring(owner=6)
        outcome = Outcome(result="WIN", cause=None, tick=tick)
        events.append(
            OutcomeEvent(
                tick=tick,
                actor=6,
                payload={"result": "WIN", "cause": None},
            )
        )
        return DispatchResult(state=engine.state, events=events, outcome=outcome)

    # 非 body_6 觸碰 → FAIL(ring_paradox) + 死亡.
    engine.update_body(body_id, status="corpse", hp=0)
    outcome = Outcome(result="FAIL", cause="ring_paradox", tick=tick)
    events.append(
        DeathEvent(
            tick=tick,
            actor=body_id,
            payload={"cause": "ring_paradox"},
        )
    )
    events.append(
        OutcomeEvent(
            tick=tick,
            actor=body_id,
            payload={"result": "FAIL", "cause": "ring_paradox"},
        )
    )
    return DispatchResult(state=engine.state, events=events, outcome=outcome)


__all__ = ["apply_touch_ring"]
