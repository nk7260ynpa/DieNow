"""PovContext 型別測試."""

from __future__ import annotations

from ring_of_hands.pov_manager.types import PovContext
from ring_of_hands.script_generator.types import Persona, Script, ScriptEvent


def _make_script(pov_id: int) -> Script:
    return Script(
        pov_id=pov_id,
        persona=Persona(name=f"p{pov_id}"),
        events=(
            ScriptEvent(t=1, actor=pov_id, action_type="wait", payload={}),
            ScriptEvent(t=2, actor=pov_id, action_type="wait", payload={}),
            ScriptEvent(t=3, actor=pov_id, action_type="die", payload={"cause": "x"}),
        ),
        death_cause="other",
    )


class TestPovContext:
    def test_next_scripted_event_for_tick_progresses(self) -> None:
        script = _make_script(1)
        ctx = PovContext(
            pov_id=1,
            persona=script.persona,
            prior_life=None,
            script=script,
        )
        e1 = ctx.next_scripted_event_for_tick(1)
        assert e1 is not None and e1["t"] == 1
        # 再次查詢 tick=1 不會重複回傳 (已推進).
        e1_again = ctx.next_scripted_event_for_tick(1)
        assert e1_again is None
        # tick=2 應回傳第二筆.
        e2 = ctx.next_scripted_event_for_tick(2)
        assert e2 is not None and e2["t"] == 2

    def test_has_pending_peek(self) -> None:
        script = _make_script(1)
        ctx = PovContext(
            pov_id=1, persona=script.persona, prior_life=None, script=script
        )
        assert ctx.has_pending_scripted_event_for_tick(1) is True
        # peek 不推進.
        assert ctx.has_pending_scripted_event_for_tick(1) is True

    def test_pov6_no_script(self) -> None:
        ctx = PovContext(pov_id=6, persona=Persona(name="agent"), prior_life=None, script=None)
        assert ctx.next_scripted_event_for_tick(1) is None
        assert not ctx.has_pending_scripted_event_for_tick(1)
