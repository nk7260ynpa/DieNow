"""Script / ScriptEvent / Persona 型別測試.

對應 spec Scenarios:
- script_1 無前世, 結構完整
- script_n (n>=2) 必帶 prior_life
- Script immutable (修改已回傳的 Script 欄位失敗)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ring_of_hands.script_generator.types import (
    Persona,
    Script,
    ScriptEvent,
)


def _make_script(pov_id: int, prior: Script | None = None) -> Script:
    return Script(
        pov_id=pov_id,
        persona=Persona(name=f"pov_{pov_id}"),
        prior_life=prior,
        events=(
            ScriptEvent(t=1, actor=pov_id, action_type="move", payload={"delta": [1, 0]}),
            ScriptEvent(
                t=10,
                actor=pov_id,
                action_type="die",
                payload={"cause": "timeout"},
            ),
        ),
        death_cause="timeout",
    )


class TestScriptImmutable:
    def test_script_frozen(self) -> None:
        script = _make_script(1)
        with pytest.raises(ValidationError):
            script.pov_id = 9  # type: ignore[misc]

    def test_script_events_tuple_immutable(self) -> None:
        script = _make_script(1)
        with pytest.raises(TypeError):
            script.events[0] = ScriptEvent(  # type: ignore[index]
                t=0, actor=1, action_type="wait"
            )


class TestScriptStructure:
    def test_script1_no_prior_life(self) -> None:
        script = _make_script(1)
        assert script.prior_life is None
        assert script.events[-1].action_type == "die"

    def test_script3_has_recursive_prior_life(self) -> None:
        s1 = _make_script(1)
        s2 = _make_script(2, prior=s1)
        s3 = _make_script(3, prior=s2)
        assert s3.prior_life is not None
        assert s3.prior_life.pov_id == 2
        assert s3.prior_life.prior_life is not None
        assert s3.prior_life.prior_life.pov_id == 1

    def test_last_event_must_be_die(self) -> None:
        with pytest.raises(ValidationError):
            Script(
                pov_id=1,
                persona=Persona(name="n"),
                events=(
                    ScriptEvent(t=1, actor=1, action_type="move", payload={"delta": [1, 0]}),
                ),
                death_cause="timeout",
            )

    def test_events_must_be_non_decreasing(self) -> None:
        with pytest.raises(ValidationError):
            Script(
                pov_id=1,
                persona=Persona(name="n"),
                events=(
                    ScriptEvent(t=5, actor=1, action_type="move", payload={"delta": [1, 0]}),
                    ScriptEvent(t=2, actor=1, action_type="die", payload={"cause": "timeout"}),
                ),
                death_cause="timeout",
            )

    def test_last_event_actor_must_match_pov(self) -> None:
        with pytest.raises(ValidationError):
            Script(
                pov_id=2,
                persona=Persona(name="n"),
                events=(
                    ScriptEvent(t=5, actor=2, action_type="move", payload={"delta": [1, 0]}),
                    ScriptEvent(t=6, actor=3, action_type="die", payload={"cause": "x"}),
                ),
                death_cause="other",
            )
