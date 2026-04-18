"""戒指觸碰規則測試.

對應 spec Scenarios:
- body_6 在條件滿足時正確拿到戒指
- 非 body_6 觸碰戒指導致 FAIL
- 防護窗未開時拒絕觸碰
"""

from __future__ import annotations

from ring_of_hands.rules_engine.ring_rule import apply_touch_ring
from ring_of_hands.world_model.engine import WorldEngine


def _all_lights_on(engine: WorldEngine) -> None:
    for i in range(1, 7):
        engine.update_button(i, lit=True)


class TestRingRule:
    def test_body6_wins(self, engine: WorldEngine) -> None:
        """body_6 於條件滿足時 WIN."""
        _all_lights_on(engine)
        engine.set_shield_open(True)
        engine.update_ring(touchable=True)
        engine.update_body(6, position=(5, 5))  # 與 ring 位置重合 (distance 0)
        result = apply_touch_ring(engine, 6)
        assert result.outcome is not None
        assert result.outcome.result == "WIN"
        assert engine.ring().owner == 6

    def test_non_body6_fails(self, engine: WorldEngine) -> None:
        """非 body_6 觸碰 → FAIL(ring_paradox) + 死亡."""
        _all_lights_on(engine)
        engine.set_shield_open(True)
        engine.update_ring(touchable=True)
        engine.update_body(3, position=(5, 5))
        result = apply_touch_ring(engine, 3)
        assert result.outcome is not None
        assert result.outcome.result == "FAIL"
        assert result.outcome.cause == "ring_paradox"
        assert engine.find_body(3).status == "corpse"

    def test_shield_closed_rejected(self, engine: WorldEngine) -> None:
        """防護窗未開時拒絕觸碰."""
        engine.update_body(6, position=(5, 5))
        result = apply_touch_ring(engine, 6)
        assert result.outcome is None
        rejected = [e for e in result.events if e.event_type == "action_rejected"]
        assert rejected and rejected[0].payload.get("reason") == "ring_not_ready"
