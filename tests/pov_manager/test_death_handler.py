"""死亡事件訂閱測試.

對應 spec:
- Corpse 更新為 is_alive=False
- 外部寫入 contexts 失敗 (MappingProxyType 保障)
"""

from __future__ import annotations

import pytest

from ring_of_hands.pov_manager.manager import PovManager
from ring_of_hands.world_model.engine import WorldEngine


class TestDeathHandler:
    def test_handle_death_marks_not_alive(
        self, engine_with_manager: tuple[WorldEngine, PovManager]
    ) -> None:
        engine, manager = engine_with_manager
        manager.handle_death(3)
        assert manager.get_context(3).is_alive is False

    def test_sync_alive_flags(
        self, engine_with_manager: tuple[WorldEngine, PovManager]
    ) -> None:
        engine, manager = engine_with_manager
        engine.update_body(2, status="corpse", hp=0)
        manager.sync_alive_flags()
        assert manager.get_context(2).is_alive is False

    def test_contexts_is_readonly(
        self, engine_with_manager: tuple[WorldEngine, PovManager]
    ) -> None:
        engine, manager = engine_with_manager
        with pytest.raises(TypeError):
            manager.contexts[2] = manager.contexts[2]  # type: ignore[index]

    def test_scripts_is_readonly(
        self, engine_with_manager: tuple[WorldEngine, PovManager]
    ) -> None:
        engine, manager = engine_with_manager
        with pytest.raises(TypeError):
            manager.scripts[2] = manager.scripts[2]  # type: ignore[index]
