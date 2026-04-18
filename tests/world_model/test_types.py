"""world_model.types 的單元測試.

對應 specs/world-model/spec.md 的 Scenarios:
- "預設 10x10 房間初始化" (部分透過 WorldState 驗證)
- "Corpse 狀態不可復活" (由 rules-engine 負責, 本處僅驗證 frozen)
- "禁止繞過 WorldEngine 直接改寫狀態"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ring_of_hands.world_model.types import (
    Body,
    Button,
    MoveAction,
    PressAction,
    Ring,
    SpeakAction,
    WorldState,
)


def _make_minimal_state() -> WorldState:
    bodies = tuple(
        Body(body_id=i + 1, position=(i, i), hp=100, number_tag=i + 1, status="alive")
        for i in range(6)
    )
    buttons = tuple(
        Button(button_id=i + 1, position=(i + 3, i + 3)) for i in range(6)
    )
    ring = Ring(position=(5, 5))
    return WorldState(
        tick=0,
        room_size=(10, 10),
        bodies=bodies,
        buttons=buttons,
        ring=ring,
    )


class TestWorldStateFrozen:
    """驗證 frozen=True 會攔截直接 mutation."""

    def test_body_is_frozen(self) -> None:
        """嘗試 mutate Body.hp 應被 Pydantic 攔截."""
        body = Body(body_id=1, position=(0, 0), hp=100, number_tag=1)
        with pytest.raises(ValidationError):
            body.hp = 0  # type: ignore[misc]

    def test_world_state_is_frozen(self) -> None:
        """WorldState 本身 frozen."""
        state = _make_minimal_state()
        with pytest.raises(ValidationError):
            state.tick = 999  # type: ignore[misc]

    def test_bodies_tuple_is_immutable(self) -> None:
        """bodies 為 tuple, 不可 .append/.pop."""
        state = _make_minimal_state()
        replacement = Body(body_id=1, position=(0, 0), hp=0, number_tag=1)
        # tuple 本身不支持 assignment by index.
        with pytest.raises(TypeError):
            state.bodies[0] = replacement  # type: ignore[index]


class TestWorldStateValidation:
    """驗證 WorldState 的資料驗證."""

    def test_wrong_body_count_rejected(self) -> None:
        """若 bodies 不足 6 個應 raise ValidationError."""
        with pytest.raises(ValidationError):
            WorldState(
                tick=0,
                room_size=(10, 10),
                bodies=(
                    Body(body_id=1, position=(0, 0), hp=100, number_tag=1),
                ),
                buttons=tuple(
                    Button(button_id=i + 1, position=(i, i)) for i in range(6)
                ),
                ring=Ring(position=(5, 5)),
            )

    def test_duplicate_body_ids_rejected(self) -> None:
        """body_id 必須為 1..6 不重覆."""
        bodies = tuple(
            Body(body_id=1, position=(i, i), hp=100, number_tag=1) for i in range(6)
        )
        with pytest.raises(ValidationError):
            WorldState(
                tick=0,
                room_size=(10, 10),
                bodies=bodies,
                buttons=tuple(
                    Button(button_id=i + 1, position=(i, i)) for i in range(6)
                ),
                ring=Ring(position=(5, 5)),
            )


class TestActionFrozen:
    """Action 家族均 frozen=True."""

    def test_move_action_frozen(self) -> None:
        action = MoveAction(delta=(1, 0))
        with pytest.raises(ValidationError):
            action.delta = (0, 1)  # type: ignore[misc]

    def test_press_action_requires_button_id(self) -> None:
        with pytest.raises(ValidationError):
            PressAction()  # type: ignore[call-arg]

    def test_speak_action_msg_default_empty_allowed_at_type_level(self) -> None:
        """型別允許空字串; 空字串的拒絕邏輯由 rules-engine 負責."""
        action = SpeakAction(msg="")
        assert action.msg == ""
