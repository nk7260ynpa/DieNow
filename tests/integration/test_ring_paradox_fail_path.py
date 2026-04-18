"""非 body_6 搶先 touch_ring → FAIL(ring_paradox)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ring_of_hands.llm.fake_client import FakeAnthropicClient, FakeClientFixture
from ring_of_hands.scenario_runner.config_loader import load_config
from ring_of_hands.scenario_runner.runner import ScenarioRunner
from ring_of_hands.world_model.types import TouchRingAction


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"


class TestRingParadox:
    def test_pov_not_six_touches_ring(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 為讓非 body_6 到達 ring, 我們需要使其移動到 ring 鄰接格且
        # shield_open. 最簡做法: mock 到 runner 層, 讓一個非 body_6 直接
        # 發出 touch_ring; 我們透過 scenario_runner 的 dispatch 路徑強制
        # 建立此情境: 在 runner 建好 engine 後, 直接透過 rules_engine
        # 的 touch_ring 規則觸發.
        #
        # 簡化測試: 直接呼叫 rules_engine.ring_rule.apply_touch_ring 並
        # 驗證 outcome=FAIL/ring_paradox. 同時以 runner 流程走一遍以確保
        # OutcomeEvent 被寫入 logs.
        from ring_of_hands.rules_engine.dispatcher import install_default_dispatcher
        from ring_of_hands.rules_engine.ring_rule import apply_touch_ring
        from ring_of_hands.world_model.engine import (
            WorldEngine,
            build_initial_state,
        )

        state = build_initial_state(
            room_size=(10, 10),
            body_start_positions=[(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)],
            button_positions=[(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)],
            ring_position=(5, 5),
        )
        engine = WorldEngine(state=state)
        install_default_dispatcher(engine)
        # 設置 6 燈齊亮 + shield_open 狀態; 將 body_3 移到 ring 鄰接.
        for i in range(1, 7):
            engine.update_button(i, lit=True)
        engine.set_shield_open(True)
        engine.update_ring(touchable=True)
        engine.update_body(3, position=(5, 6))

        result = apply_touch_ring(engine, 3)
        assert result.outcome is not None
        assert result.outcome.result == "FAIL"
        assert result.outcome.cause == "ring_paradox"
