"""死亡規則測試.

對應 spec Scenarios:
- Corpse 狀態不可復活 (IllegalStateTransition)
"""

from __future__ import annotations

import pytest

from ring_of_hands.rules_engine.death_rule import ensure_not_resurrection, kill_body
from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import IllegalStateTransition


class TestDeathRule:
    def test_kill_body_sets_corpse(self, engine: WorldEngine) -> None:
        event = kill_body(engine, 5, cause="press_wrong")
        assert engine.find_body(5).status == "corpse"
        assert engine.find_body(5).hp == 0
        assert event.payload.get("cause") == "press_wrong"

    def test_cannot_kill_twice(self, engine: WorldEngine) -> None:
        kill_body(engine, 5, cause="press_wrong")
        with pytest.raises(IllegalStateTransition):
            kill_body(engine, 5, cause="press_wrong")

    def test_ensure_not_resurrection(self) -> None:
        with pytest.raises(IllegalStateTransition):
            ensure_not_resurrection("corpse", "alive")
        # alive → corpse 合法.
        ensure_not_resurrection("alive", "corpse")
