"""pov_6 自由 agent 流程測試.

對應 spec:
- pov_6 每 tick 一次自由決策
- pov_6 回傳非法 action 降級為 wait
"""

from __future__ import annotations

import pytest

from ring_of_hands.pov_manager.manager import PovManager
from ring_of_hands.pov_manager.types import PovContext  # noqa: F401  (for completeness)
from ring_of_hands.rules_engine.dispatcher import install_default_dispatcher
from ring_of_hands.script_generator.types import Persona
from ring_of_hands.world_model.engine import WorldEngine, build_initial_state
from ring_of_hands.world_model.types import Action, ActionDowngradedEvent, WaitAction


# 為了不重複依賴 conftest 的 make_simple_scripts, 本檔 import 它.
from tests.pov_manager.conftest import (
    BODY_POS,
    BUTTON_POS,
    RING_POS,
    ROOM,
    make_simple_scripts,
)


def _build_manager(agent_decide_fn):
    state = build_initial_state(
        room_size=ROOM,
        body_start_positions=BODY_POS,
        button_positions=BUTTON_POS,
        ring_position=RING_POS,
    )
    engine = WorldEngine(state=state)
    manager = PovManager(
        engine=engine,
        scripts=make_simple_scripts(),
        pov6_persona=Persona(name="agent"),
        agent_decide_fn=agent_decide_fn,
    )
    install_default_dispatcher(
        engine, context_provider=manager.consume_dispatch_context
    )
    return engine, manager


class TestFreeAgent:
    def test_pov6_called_once_per_tick(self) -> None:
        calls: list[int] = []

        def decide(pov_id: int, observation: object) -> Action:
            calls.append(pov_id)
            return WaitAction()

        engine, manager = _build_manager(decide)
        engine.advance_tick()
        manager.tick_free_agent(engine.state.tick)
        assert calls == [6]

    def test_pov6_exception_downgrades_to_wait(self) -> None:
        def decide(pov_id: int, observation: object) -> Action:
            raise RuntimeError("llm parse fail")

        engine, manager = _build_manager(decide)
        engine.advance_tick()
        manager.tick_free_agent(engine.state.tick)
        # 應有 ActionDowngradedEvent.
        events = engine.event_log.in_memory_events
        assert any(e.get("event_type") == "action_downgraded" for e in events)

    def test_pov6_dead_skipped(self) -> None:
        calls: list[int] = []

        def decide(pov_id: int, observation: object) -> Action:
            calls.append(pov_id)
            return WaitAction()

        engine, manager = _build_manager(decide)
        engine.update_body(6, status="corpse", hp=0)
        manager.sync_alive_flags()
        engine.advance_tick()
        manager.tick_free_agent(engine.state.tick)
        assert calls == []

    def test_pov6_inv7_on_duplicate_dispatch(self) -> None:
        def decide(pov_id: int, observation: object) -> Action:
            return WaitAction()

        engine, manager = _build_manager(decide)
        engine.advance_tick()
        manager.tick_free_agent(engine.state.tick)
        # 第二次呼叫應觸發 INV-7.
        from ring_of_hands.world_model.types import InvariantViolation

        with pytest.raises(InvariantViolation):
            manager.tick_free_agent(engine.state.tick)
