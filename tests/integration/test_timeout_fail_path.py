"""pov_6 永遠 Wait → FAIL(timeout)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ring_of_hands.llm.fake_client import FakeClientFixture, FakeLLMClient
from ring_of_hands.scenario_runner.config_loader import load_config
from ring_of_hands.scenario_runner.runner import ScenarioRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"


class TestTimeoutFailPath:
    def test_wait_forever_timeout(self, tmp_path: Path) -> None:
        # fixture: pov_1..5 不按按鈕 (無 press events; 僅 die marker);
        # pov_6 永遠 wait. 6 燈永遠亮不起來, 也不會 unreachable (因為所有
        # pov 都活著, button 未亮但對應 body 還活). → timeout.
        scripts = []
        for i in range(1, 6):
            scripts.append(
                {
                    "pov_id": i,
                    "persona": {"name": f"p{i}"},
                    "events": [
                        {"t": 1, "actor": i, "action_type": "wait", "payload": {}},
                        {
                            "t": 50,
                            "actor": i,
                            "action_type": "die",
                            "payload": {"cause": "timeout"},
                        },
                    ],
                    "death_cause": "timeout",
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
        assert summary.outcome.cause == "timeout"
