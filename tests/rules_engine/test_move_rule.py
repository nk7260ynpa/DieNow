"""移動與碰撞規則測試.

對應 spec Scenarios:
- 合法移動成功
- 與 corpse 碰撞時拒絕
- 越界拒絕
"""

from __future__ import annotations

from ring_of_hands.rules_engine.move_rule import apply_move
from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import MoveAction


class TestMoveRule:
    def test_legal_move(self, engine: WorldEngine) -> None:
        """合法移動更新位置並產生 MoveEvent."""
        engine.update_body(1, position=(2, 2))
        result = apply_move(engine, 1, MoveAction(delta=(1, 0)))
        assert engine.find_body(1).position == (3, 2)
        types = [e.event_type for e in result.events]
        assert "move" in types

    def test_collision_with_corpse_rejected(self, engine: WorldEngine) -> None:
        """目標格被 corpse 佔用 → 拒絕."""
        engine.update_body(1, position=(2, 2))
        engine.update_body(5, position=(3, 2), status="corpse")
        result = apply_move(engine, 1, MoveAction(delta=(1, 0)))
        assert engine.find_body(1).position == (2, 2)
        rejected = [e for e in result.events if e.event_type == "action_rejected"]
        assert rejected and rejected[0].payload.get("reason") == "collision"

    def test_out_of_bounds_rejected(self, engine: WorldEngine) -> None:
        """向左超出 0 → 拒絕."""
        engine.update_body(1, position=(0, 0))
        result = apply_move(engine, 1, MoveAction(delta=(-1, 0)))
        assert engine.find_body(1).position == (0, 0)
        rejected = [e for e in result.events if e.event_type == "action_rejected"]
        assert rejected and rejected[0].payload.get("reason") == "out_of_bounds"

    def test_wait_in_place_allowed(self, engine: WorldEngine) -> None:
        """delta=(0,0) 相當於原地不動, 不產生 rejected."""
        engine.update_body(1, position=(2, 2))
        result = apply_move(engine, 1, MoveAction(delta=(0, 0)))
        assert engine.find_body(1).position == (2, 2)
        types = [e.event_type for e in result.events]
        # 原地但仍產生 move event (記 audit).
        assert "move" in types

    def test_cannot_walk_onto_button(self, engine: WorldEngine) -> None:
        """按鈕格禁止踩上去."""
        engine.update_body(1, position=(1, 2))  # button_1 位於 (2,2)
        result = apply_move(engine, 1, MoveAction(delta=(1, 0)))
        assert engine.find_body(1).position == (1, 2)
        rejected = [e for e in result.events if e.event_type == "action_rejected"]
        assert rejected and rejected[0].payload.get("reason") == "collision"
