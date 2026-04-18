"""時間一致性驗證器測試.

對應 spec Scenarios:
- 閉環一致時驗證通過
- 閉環不一致時驗證失敗並回傳 diff
"""

from __future__ import annotations

from ring_of_hands.script_generator.types import Persona, Script, ScriptEvent
from ring_of_hands.script_generator.validator import validate_closure


def _script_with_events(pov_id: int, events: list[ScriptEvent], prior: Script | None = None) -> Script:
    return Script(
        pov_id=pov_id,
        persona=Persona(name=f"p{pov_id}"),
        prior_life=prior,
        events=tuple(events),
        death_cause="timeout",
    )


class TestValidator:
    def test_pov1_always_valid(self) -> None:
        s1 = _script_with_events(
            1, [ScriptEvent(t=1, actor=1, action_type="die", payload={"cause": "x"})]
        )
        result = validate_closure(current=s1, prior=None)
        assert result.valid

    def test_closed_loop_valid(self) -> None:
        shared_event = ScriptEvent(
            t=3,
            actor=2,
            action_type="speak",
            payload={"msg": "hi"},
            targets=(1,),
        )
        s1 = _script_with_events(
            1,
            [
                shared_event,
                ScriptEvent(t=5, actor=1, action_type="die", payload={"cause": "x"}),
            ],
        )
        s2 = _script_with_events(
            2,
            [
                shared_event,
                ScriptEvent(t=10, actor=2, action_type="die", payload={"cause": "y"}),
            ],
            prior=s1,
        )
        result = validate_closure(current=s2, prior=s1)
        assert result.valid
        assert not result.diff

    def test_payload_conflict_returns_diff(self) -> None:
        event_prior = ScriptEvent(
            t=3,
            actor=2,
            action_type="speak",
            payload={"msg": "hi"},
            targets=(1,),
        )
        event_current = ScriptEvent(
            t=3,
            actor=2,
            action_type="speak",
            payload={"msg": "hello"},
            targets=(1,),
        )
        s1 = _script_with_events(
            1,
            [
                event_prior,
                ScriptEvent(t=5, actor=1, action_type="die", payload={"cause": "x"}),
            ],
        )
        s2 = _script_with_events(
            2,
            [
                event_current,
                ScriptEvent(t=10, actor=2, action_type="die", payload={"cause": "y"}),
            ],
            prior=s1,
        )
        result = validate_closure(current=s2, prior=s1)
        assert not result.valid
        # diff 含 payload 差異.
        assert any(d.get("field") == "payload" for d in result.diff)

    def test_missing_in_current_returns_diff(self) -> None:
        event_in_prior_only = ScriptEvent(
            t=3,
            actor=1,
            action_type="speak",
            payload={"msg": "miss"},
            targets=(2,),
        )
        s1 = _script_with_events(
            1,
            [
                event_in_prior_only,
                ScriptEvent(t=5, actor=1, action_type="die", payload={"cause": "x"}),
            ],
        )
        s2 = _script_with_events(
            2,
            [
                ScriptEvent(
                    t=10, actor=2, action_type="die", payload={"cause": "y"}
                ),
            ],
            prior=s1,
        )
        result = validate_closure(current=s2, prior=s1)
        assert not result.valid
        assert any(
            d.get("direction") == "prior_missing_in_current" for d in result.diff
        )
