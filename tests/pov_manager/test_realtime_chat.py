"""即時對話路由測試.

對應 spec:
- 正常即時回應
- 即時回應與 script 衝突時降級
- enable_realtime_chat=false 時不呼叫 LLM
"""

from __future__ import annotations

from ring_of_hands.pov_manager.manager import PovManager
from ring_of_hands.rules_engine.dispatcher import install_default_dispatcher
from ring_of_hands.script_generator.types import Persona, Script, ScriptEvent
from ring_of_hands.world_model.engine import WorldEngine, build_initial_state
from ring_of_hands.world_model.types import Action, SpeakAction, WaitAction


from tests.pov_manager.conftest import (
    BODY_POS,
    BUTTON_POS,
    RING_POS,
    ROOM,
)


def _scripts_with_pending_press() -> list[Script]:
    scripts: list[Script] = []
    prior = None
    for pov_id in range(1, 6):
        script = Script(
            pov_id=pov_id,
            persona=Persona(name=f"p{pov_id}"),
            prior_life=prior,
            events=(
                ScriptEvent(t=1, actor=pov_id, action_type="wait", payload={}),
                ScriptEvent(
                    t=5,
                    actor=pov_id,
                    action_type="press",
                    payload={"button_id": pov_id},
                ),
                ScriptEvent(
                    t=10,
                    actor=pov_id,
                    action_type="die",
                    payload={"cause": "timeout"},
                ),
            ),
            death_cause="timeout",
        )
        scripts.append(script)
        prior = script
    return scripts


def _build(enable_chat: bool = True, realtime_reply_fn=None):
    state = build_initial_state(
        room_size=ROOM,
        body_start_positions=BODY_POS,
        button_positions=BUTTON_POS,
        ring_position=RING_POS,
    )
    engine = WorldEngine(state=state)
    manager = PovManager(
        engine=engine,
        scripts=_scripts_with_pending_press(),
        pov6_persona=Persona(name="agent"),
        agent_decide_fn=lambda _pov, _obs: WaitAction(),
        realtime_reply_fn=realtime_reply_fn,
        enable_realtime_chat=enable_chat,
    )
    install_default_dispatcher(
        engine, context_provider=manager.consume_dispatch_context
    )
    return engine, manager


class TestRealtimeChat:
    def test_normal_reply(self) -> None:
        called: list[tuple[int, dict]] = []

        def reply(pov_id: int, kwargs: dict) -> str:
            called.append((pov_id, kwargs))
            return "我不確定."

        engine, manager = _build(True, reply)
        events = manager.request_realtime_reply(
            3, SpeakAction(msg="你記得上一世嗎?", targets=(3,))
        )
        assert called and called[0][0] == 3
        assert any(e.event_type == "speak" for e in events)

    def test_conflict_downgrade(self) -> None:
        def reply(pov_id: int, kwargs: dict) -> str:
            return "我要去拿戒指"

        engine, manager = _build(True, reply)
        events = manager.request_realtime_reply(
            3, SpeakAction(msg="下一步?", targets=(3,))
        )
        downgrades = [e for e in events if e.event_type == "action_downgraded"]
        assert downgrades
        speaks = [e for e in events if e.event_type == "speak"]
        assert speaks and speaks[0].payload["msg"] == "..."

    def test_disabled(self) -> None:
        def reply(pov_id: int, kwargs: dict) -> str:
            return "shouldn't be called"

        engine, manager = _build(False, reply)
        events = manager.request_realtime_reply(
            3, SpeakAction(msg="hi", targets=(3,))
        )
        assert events == []

    def test_dead_target_skipped(self) -> None:
        def reply(pov_id: int, kwargs: dict) -> str:
            return "我還好"

        engine, manager = _build(True, reply)
        engine.update_body(3, status="corpse", hp=0)
        manager.sync_alive_flags()
        events = manager.request_realtime_reply(
            3, SpeakAction(msg="hi", targets=(3,))
        )
        assert events == []
