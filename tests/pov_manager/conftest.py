"""pov_manager 測試共用 fixture."""

from __future__ import annotations

import pytest

from ring_of_hands.pov_manager.manager import PovManager
from ring_of_hands.rules_engine.dispatcher import install_default_dispatcher
from ring_of_hands.script_generator.types import Persona, Script, ScriptEvent
from ring_of_hands.world_model.engine import WorldEngine, build_initial_state
from ring_of_hands.world_model.types import Action, WaitAction


ROOM = (10, 10)
BODY_POS = [(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)]
BUTTON_POS = [(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)]
RING_POS = (5, 5)


def make_simple_scripts() -> list[Script]:
    """產出 5 份簡單 script.

    每個 pov_n 於 tick 1 press button_n, tick 10 die(timeout).
    body_n 起始在 BODY_POS[n-1], button_n 在 BUTTON_POS[n-1], 距離合法.
    但注意這些 pos 對本 fixture 測試僅用來檢驗 PovManager 的 tick 分派邏輯,
    實際 dispatch 成功與否視 rules_engine 而定.
    """
    scripts: list[Script] = []
    prior: Script | None = None
    for pov_id in range(1, 6):
        script = Script(
            pov_id=pov_id,
            persona=Persona(name=f"pov_{pov_id}"),
            prior_life=prior,
            events=(
                ScriptEvent(
                    t=1,
                    actor=pov_id,
                    action_type="wait",
                    payload={},
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


@pytest.fixture
def engine_with_manager() -> tuple[WorldEngine, PovManager]:
    state = build_initial_state(
        room_size=ROOM,
        body_start_positions=BODY_POS,
        button_positions=BUTTON_POS,
        ring_position=RING_POS,
    )
    engine = WorldEngine(state=state)
    # 簡單的 agent_decide_fn: 永遠回 WaitAction.
    def decide(pov_id: int, observation: object) -> Action:
        return WaitAction()

    scripts = make_simple_scripts()
    pov6_persona = Persona(name="被困的玩家")
    manager = PovManager(
        engine=engine,
        scripts=scripts,
        pov6_persona=pov6_persona,
        agent_decide_fn=decide,
    )
    install_default_dispatcher(
        engine,
        context_provider=manager.consume_dispatch_context,
    )
    return engine, manager
