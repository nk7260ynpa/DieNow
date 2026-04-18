"""rules_engine 測試共用 fixture."""

from __future__ import annotations

import pytest

from ring_of_hands.rules_engine.dispatcher import install_default_dispatcher
from ring_of_hands.world_model.engine import WorldEngine, build_initial_state


ROOM = (10, 10)
BODY_POS = [(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)]
BUTTON_POS = [(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)]
RING_POS = (5, 5)


@pytest.fixture
def engine() -> WorldEngine:
    """建立已注入預設 dispatcher 的 WorldEngine."""
    state = build_initial_state(
        room_size=ROOM,
        body_start_positions=BODY_POS,
        button_positions=BUTTON_POS,
        ring_position=RING_POS,
    )
    eng = WorldEngine(state=state)
    install_default_dispatcher(eng)
    return eng
