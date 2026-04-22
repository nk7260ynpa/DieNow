"""ScenarioRunner 整合流程測試."""

from __future__ import annotations

from pathlib import Path

import pytest

from ring_of_hands.llm.fake_client import FakeClientFixture, FakeLLMClient
from ring_of_hands.scenario_runner.config_loader import load_config
from ring_of_hands.scenario_runner.runner import ScenarioRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def dry_run_config():
    return load_config(
        CONFIGS_DIR / "default.yaml",
        personas_path=CONFIGS_DIR / "personas.yaml",
        dry_run=True,
    )


class TestScenarioRunner:
    def test_dry_run_win(self, dry_run_config, tmp_path: Path) -> None:
        """dry_run 下以 dry_run.yaml 跑到 WIN."""
        fixture = FakeClientFixture.from_yaml(FIXTURES_DIR / "dry_run.yaml")
        runner = ScenarioRunner(
            dry_run_config,
            log_dir=tmp_path / "logs",
            llm_client_override=FakeLLMClient(fixture),
            fake_fixture_override=fixture,
        )
        summary = runner.run()
        assert summary.outcome.result == "WIN", summary.model_dump()
        assert summary.lit_buttons_at_end == 6
        # Logs 應存在.
        assert Path(summary.event_log_path).exists()
