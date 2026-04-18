"""scripted pov 劇本執行器測試.

對應 spec:
- tick 命中時按劇本 dispatch
- 死亡 pov 略過劇本
"""

from __future__ import annotations

from ring_of_hands.pov_manager.manager import PovManager
from ring_of_hands.world_model.engine import WorldEngine


class TestScriptedExecutor:
    def test_tick_scripted_dispatches(
        self, engine_with_manager: tuple[WorldEngine, PovManager]
    ) -> None:
        engine, manager = engine_with_manager
        engine.advance_tick()  # tick=1
        manager.tick_scripted_povs(1)
        # 每個 pov_1..5 於 tick 1 有 wait event; wait 不產生事件但 dispatch 成功.
        # 驗證所有 pov 的 _executed_event_count 都 >=1.
        for pov_id in range(1, 6):
            ctx = manager.get_context(pov_id)
            assert ctx._executed_event_count >= 1

    def test_dead_pov_skipped(
        self, engine_with_manager: tuple[WorldEngine, PovManager]
    ) -> None:
        engine, manager = engine_with_manager
        # 標記 pov_3 死亡.
        engine.update_body(3, status="corpse", hp=0)
        manager.sync_alive_flags()
        engine.advance_tick()  # tick=1
        manager.tick_scripted_povs(1)
        # pov_3 不應被推進.
        ctx3 = manager.get_context(3)
        assert ctx3._executed_event_count == 0
        # pov_1, 2, 4, 5 應被推進.
        for pov_id in (1, 2, 4, 5):
            assert manager.get_context(pov_id)._executed_event_count >= 1

    def test_outcome_stops_iteration(
        self, engine_with_manager: tuple[WorldEngine, PovManager]
    ) -> None:
        engine, manager = engine_with_manager
        from ring_of_hands.world_model.types import Outcome

        engine.set_outcome(Outcome(result="WIN", tick=0))
        engine.advance_tick()
        # tick_scripted_povs 直接 return.
        manager.tick_scripted_povs(1)
        for pov_id in range(1, 6):
            assert manager.get_context(pov_id)._executed_event_count == 0
