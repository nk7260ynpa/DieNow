"""body_3 死亡且 button_3 未亮 → 提前 FAIL(unreachable_six_lights)."""

from __future__ import annotations

from pathlib import Path

from ring_of_hands.llm.fake_client import FakeClientFixture, FakeLLMClient
from ring_of_hands.scenario_runner.config_loader import load_config
from ring_of_hands.scenario_runner.runner import ScenarioRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"


class TestUnreachableSixLights:
    def test_body3_dies_before_pressing(self, tmp_path: Path) -> None:
        # 讓 pov_3 按錯按鈕: body_3 起始 (4,1), button_1 不鄰接.
        # 改為: pov_3 press button_2 (距離遠, 視為 out_of_range 被拒絕).
        # 我們改讓 pov_3 press button_2 但先移到 button_2 鄰接位置 → 按錯
        # 死亡 (按錯→corpse).
        scripts = []
        for i in range(1, 6):
            events = []
            if i == 3:
                # pov_3 移到 (3, 1) 鄰接 button_1=(2,2) (distance=1).
                events = [
                    {
                        "t": 1,
                        "actor": 3,
                        "action_type": "move",
                        "payload": {"delta": [-1, 0]},
                        "targets": [],
                    },
                    {
                        "t": 2,
                        "actor": 3,
                        "action_type": "press",
                        "payload": {"button_id": 1},
                        "targets": [],
                    },
                    {
                        "t": 50,
                        "actor": 3,
                        "action_type": "die",
                        "payload": {"cause": "press_wrong"},
                        "targets": [],
                    },
                ]
            else:
                events = [
                    {"t": 1, "actor": i, "action_type": "wait", "payload": {}},
                    {
                        "t": 50,
                        "actor": i,
                        "action_type": "die",
                        "payload": {"cause": "timeout"},
                        "targets": [],
                    },
                ]
            scripts.append(
                {
                    "pov_id": i,
                    "persona": {"name": f"p{i}"},
                    "events": events,
                    "death_cause": "press_wrong" if i == 3 else "timeout",
                }
            )
        fixture = FakeClientFixture(
            scripts=scripts,
            project_agent_actions=[{"action": "wait"}] * 60,
        )
        config = load_config(
            CONFIGS_DIR / "default.yaml",
            personas_path=CONFIGS_DIR / "personas.yaml",
            dry_run=True,
        )
        runner = ScenarioRunner(
            config,
            log_dir=tmp_path / "logs",
            llm_client_override=FakeLLMClient(fixture),
            fake_fixture_override=fixture,
        )
        summary = runner.run()
        assert summary.outcome.result == "FAIL"
        assert summary.outcome.cause == "unreachable_six_lights"
