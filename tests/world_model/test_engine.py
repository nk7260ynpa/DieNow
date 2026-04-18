"""WorldEngine 的基礎單元測試 (未注入 rules-engine).

dispatch 行為的完整測試於 tests/rules_engine 測試.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ring_of_hands.world_model.engine import WorldEngine, build_initial_state
from ring_of_hands.world_model.types import (
    InvariantViolation,
    MoveAction,
)


DEFAULT_ROOM = (10, 10)
DEFAULT_BODY_POS = [(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)]
DEFAULT_BUTTON_POS = [(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)]
DEFAULT_RING_POS = (5, 5)


def _engine() -> WorldEngine:
    state = build_initial_state(
        room_size=DEFAULT_ROOM,
        body_start_positions=DEFAULT_BODY_POS,
        button_positions=DEFAULT_BUTTON_POS,
        ring_position=DEFAULT_RING_POS,
    )
    return WorldEngine(state=state)


class TestWorldEngineStateFrozen:
    def test_cannot_mutate_state_directly(self) -> None:
        """外部嘗試直接改寫 state 欄位會被 Pydantic 攔截."""
        engine = _engine()
        with pytest.raises(ValidationError):
            engine.state.tick = 999  # type: ignore[misc]

    def test_cannot_mutate_body_directly(self) -> None:
        engine = _engine()
        with pytest.raises(ValidationError):
            engine.state.bodies[0].hp = 0  # type: ignore[misc]


class TestWorldEngineAdvanceTick:
    def test_advance_tick_increments(self) -> None:
        engine = _engine()
        assert engine.state.tick == 0
        engine.advance_tick()
        assert engine.state.tick == 1

    def test_advance_tick_resets_free_actions(self) -> None:
        engine = _engine()
        engine.register_free_action(6)
        assert 6 in engine.state.free_actions_this_tick
        engine.advance_tick()
        assert engine.state.free_actions_this_tick == ()


class TestWorldEngineDispatcherRequired:
    def test_dispatch_without_dispatcher_raises(self) -> None:
        """尚未注入 dispatcher 時 dispatch 應 raise."""
        engine = _engine()
        with pytest.raises(RuntimeError):
            engine.dispatch(1, MoveAction(delta=(1, 0)))


class TestConfigValidation:
    def test_out_of_bounds_body_rejected(self) -> None:
        """body 座標超出房間大小應 raise ValueError."""
        with pytest.raises(ValueError):
            build_initial_state(
                room_size=(10, 10),
                body_start_positions=[(15, 5), *DEFAULT_BODY_POS[1:]],
                button_positions=DEFAULT_BUTTON_POS,
                ring_position=DEFAULT_RING_POS,
            )


class TestInv7:
    """INV-7: 同一 tick 對同一 pov 僅接受 1 次自由 action."""

    def test_duplicate_free_action_raises(self) -> None:
        engine = _engine()
        engine.register_free_action(6)
        with pytest.raises(InvariantViolation) as exc_info:
            engine.register_free_action(6)
        assert exc_info.value.inv_id == "INV-7"

    def test_advance_tick_clears_free_actions(self) -> None:
        engine = _engine()
        engine.register_free_action(6)
        engine.advance_tick()
        # 新 tick 可再次登記.
        engine.register_free_action(6)
