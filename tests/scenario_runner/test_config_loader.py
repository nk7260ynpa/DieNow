"""config_loader 測試."""

from __future__ import annotations

from pathlib import Path

import pytest

from ring_of_hands.scenario_runner.config_loader import (
    ConfigValidationError,
    FixtureNotFoundError,
    load_config,
)


@pytest.fixture
def configs_dir(tmp_path: Path) -> Path:
    """建立臨時 configs 目錄."""
    d = tmp_path / "configs"
    d.mkdir()

    (d / "default.yaml").write_text(
        """
room_size: [10, 10]
body_start_positions: [[1,1],[1,8],[4,1],[4,8],[8,1],[8,8]]
button_positions: [[2,2],[2,7],[5,2],[5,7],[7,2],[7,7]]
ring_position: [5,5]
max_ticks: 50
max_retries: 3
enable_realtime_chat: true
llm_client: fake
project_agent_model: claude-sonnet-4-7
dry_run_fixture_path: tests/fixtures/dry_run.yaml
pov6_persona:
  name: 被困的玩家
  description: d
  traits: [cautious]
""",
        encoding="utf-8",
    )
    (d / "personas.yaml").write_text(
        """
personas:
  - {name: 新生, description: x, traits: [curious]}
  - {name: 追憶者, description: x, traits: [cautious]}
  - {name: 懷疑者, description: x, traits: [suspicious]}
  - {name: 觀察者, description: x, traits: [patient]}
  - {name: 預知者, description: x, traits: [calculating]}
""",
        encoding="utf-8",
    )
    return d


class TestLoadConfig:
    def test_success_with_fake_llm(self, configs_dir: Path) -> None:
        cfg = load_config(
            configs_dir / "default.yaml",
            env_overrides={"ANTHROPIC_API_KEY": ""},
        )
        assert cfg.llm_client == "fake"
        assert len(cfg.pov1_to_5_personas) == 5

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigValidationError):
            load_config(tmp_path / "missing.yaml")

    def test_anthropic_without_api_key_raises(self, tmp_path: Path) -> None:
        configs = tmp_path / "configs"
        configs.mkdir()
        (configs / "default.yaml").write_text(
            """
room_size: [10, 10]
body_start_positions: [[1,1],[1,8],[4,1],[4,8],[8,1],[8,8]]
button_positions: [[2,2],[2,7],[5,2],[5,7],[7,2],[7,7]]
ring_position: [5,5]
llm_client: anthropic
pov6_persona: {name: a, description: "", traits: []}
""",
            encoding="utf-8",
        )
        (configs / "personas.yaml").write_text(
            "personas:\n"
            + "\n".join(
                f"  - {{name: p{i}, description: '', traits: []}}"
                for i in range(1, 6)
            ),
            encoding="utf-8",
        )
        with pytest.raises(ConfigValidationError):
            load_config(
                configs / "default.yaml",
                env_overrides={"ANTHROPIC_API_KEY": ""},
            )

    def test_dry_run_missing_fixture(self, configs_dir: Path, tmp_path: Path) -> None:
        # 建立一份 config 但 dry-run fixture 指向不存在路徑.
        (configs_dir / "default.yaml").write_text(
            """
room_size: [10, 10]
body_start_positions: [[1,1],[1,8],[4,1],[4,8],[8,1],[8,8]]
button_positions: [[2,2],[2,7],[5,2],[5,7],[7,2],[7,7]]
ring_position: [5,5]
llm_client: fake
project_agent_model: claude-sonnet-4-7
dry_run_fixture_path: nope/missing.yaml
pov6_persona: {name: a, description: "", traits: []}
""",
            encoding="utf-8",
        )
        with pytest.raises(FixtureNotFoundError):
            load_config(configs_dir / "default.yaml", dry_run=True)
