"""Observation 建構器測試.

對應 specs/world-model/spec.md:
- "透過 observe 介面讀取自身視角"
- "Corpse 狀態不可復活" (部分)
- specs/rules-engine/spec.md 的 INV-5 攔截.
"""

from __future__ import annotations

from ring_of_hands.world_model.engine import build_initial_state
from ring_of_hands.world_model.observation import build_observation


DEFAULT_ROOM = (10, 10)
DEFAULT_BODY_POS = [(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)]
DEFAULT_BUTTON_POS = [(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)]
DEFAULT_RING_POS = (5, 5)


def _state():
    return build_initial_state(
        room_size=DEFAULT_ROOM,
        body_start_positions=DEFAULT_BODY_POS,
        button_positions=DEFAULT_BUTTON_POS,
        ring_position=DEFAULT_RING_POS,
    )


class TestBuildObservation:
    def test_pov3_sees_self_and_others(self) -> None:
        """pov_3 能看到自己位置與其他 5 個 body."""
        state = _state()
        obs = build_observation(state, pov_id=3)
        assert obs.pov_id == 3
        assert obs.self_position == (4, 1)
        assert len(obs.other_bodies) == 5
        ids = sorted(b.body_id for b in obs.other_bodies)
        assert ids == [1, 2, 4, 5, 6]

    def test_observation_does_not_expose_self_number_tag(self) -> None:
        """observation 結構不含 self_number_tag 欄位 (INV-5)."""
        state = _state()
        obs = build_observation(state, pov_id=3)
        payload = obs.model_dump()
        assert "self_number_tag" not in payload
        assert "rules" not in payload
        assert "goal" not in payload

    def test_other_bodies_expose_number_tag(self) -> None:
        """其他 body 的號碼牌可見."""
        state = _state()
        obs = build_observation(state, pov_id=3)
        for snapshot in obs.other_bodies:
            assert snapshot.number_tag in {1, 2, 4, 5, 6}

    def test_prior_life_summary_passed_through(self) -> None:
        """prior_life_summary 由呼叫端注入."""
        state = _state()
        obs = build_observation(
            state, pov_id=6, prior_life_summary="5 層遞迴前世記憶摘要..."
        )
        assert obs.self_prior_life_summary is not None
