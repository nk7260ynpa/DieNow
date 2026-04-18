"""config_loader 測試.

對應本 change (`migrate-to-claude-cli-subprocess`) 的 scenario-runner spec:
- 預設設定啟動成功 (dry-run, fake client).
- 缺少 config 檔時 raise ConfigValidationError.
- llm_client="claude_cli" 且 CLI 不存在時 raise ConfigValidationError.
- llm_client="claude_cli" 且 ~/.claude/ 不存在時 raise ConfigValidationError.
- dry-run 模式下 MUST 跳過 CLI 相關檢查.
- CLAUDE_CLI_TIMEOUT_SECONDS 覆寫預設 timeout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ring_of_hands.scenario_runner.config_loader import (
    ConfigValidationError,
    FixtureNotFoundError,
    load_config,
)


CONFIG_YAML = """
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
"""


PERSONAS_YAML = """
personas:
  - {name: 新生, description: x, traits: [curious]}
  - {name: 追憶者, description: x, traits: [cautious]}
  - {name: 懷疑者, description: x, traits: [suspicious]}
  - {name: 觀察者, description: x, traits: [patient]}
  - {name: 預知者, description: x, traits: [calculating]}
"""


@pytest.fixture
def configs_dir(tmp_path: Path) -> Path:
    """建立臨時 configs 目錄."""
    d = tmp_path / "configs"
    d.mkdir()
    (d / "default.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    (d / "personas.yaml").write_text(PERSONAS_YAML, encoding="utf-8")
    return d


class TestLoadConfigBasic:
    def test_success_with_fake_llm(self, configs_dir: Path) -> None:
        cfg = load_config(configs_dir / "default.yaml")
        assert cfg.llm_client == "fake"
        assert len(cfg.pov1_to_5_personas) == 5

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigValidationError):
            load_config(tmp_path / "missing.yaml")

    def test_legacy_anthropic_value_converted_to_claude_cli(
        self, configs_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """舊 YAML 寫 "anthropic" 會被轉為 "claude_cli"."""
        (configs_dir / "default.yaml").write_text(
            CONFIG_YAML.replace("llm_client: fake", "llm_client: anthropic"),
            encoding="utf-8",
        )
        cfg = load_config(
            configs_dir / "default.yaml", skip_cli_checks=True
        )
        assert cfg.llm_client == "claude_cli"


class TestClaudeCliValidation:
    def _write_cli_cfg(self, configs_dir: Path) -> None:
        (configs_dir / "default.yaml").write_text(
            CONFIG_YAML.replace("llm_client: fake", "llm_client: claude_cli"),
            encoding="utf-8",
        )

    def test_cli_not_in_path_raises(
        self,
        configs_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """缺 `claude` 指令 → ConfigValidationError."""
        self._write_cli_cfg(configs_dir)
        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.shutil.which",
            lambda _: None,
        )
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config(configs_dir / "default.yaml")
        assert "claude CLI 不可執行" in str(excinfo.value)

    def test_version_nonzero_raises(
        self,
        configs_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`claude --version` 非零退出 → ConfigValidationError."""
        self._write_cli_cfg(configs_dir)
        import subprocess

        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.shutil.which",
            lambda p: p,
        )

        def _fake_run(*a, **kw):
            return subprocess.CompletedProcess(
                args=a[0], returncode=1, stdout="", stderr="err"
            )

        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.subprocess.run",
            _fake_run,
        )
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config(configs_dir / "default.yaml")
        assert "退出碼 1" in str(excinfo.value)

    def test_claude_home_missing_raises(
        self,
        configs_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """~/.claude/ 不存在 → ConfigValidationError."""
        self._write_cli_cfg(configs_dir)
        import subprocess

        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.shutil.which",
            lambda p: p,
        )

        def _fake_run(*a, **kw):
            return subprocess.CompletedProcess(
                args=a[0], returncode=0, stdout="1.0", stderr=""
            )

        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.subprocess.run",
            _fake_run,
        )
        monkeypatch.setenv("CLAUDE_HOME", str(tmp_path / "nope"))
        with pytest.raises(ConfigValidationError) as excinfo:
            load_config(configs_dir / "default.yaml")
        assert "請先執行 `claude login`" in str(excinfo.value)

    def test_dry_run_skips_cli_checks(
        self, configs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """dry-run 模式 MUST 跳過 Claude CLI 預啟動檢查."""
        self._write_cli_cfg(configs_dir)
        # 模擬 CLI 不存在.
        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.shutil.which",
            lambda _: None,
        )
        # dry-run 應仍能成功載入.
        cfg = load_config(configs_dir / "default.yaml", dry_run=True)
        assert cfg.llm_client == "fake"
        assert cfg.dry_run is True

    def test_successful_startup_with_valid_cli_env(
        self,
        configs_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """CLI 與 ~/.claude 都就緒時 claude_cli 可啟動."""
        self._write_cli_cfg(configs_dir)
        fake_home = tmp_path / ".claude"
        fake_home.mkdir()
        import subprocess

        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.shutil.which",
            lambda p: p,
        )

        def _fake_run(*a, **kw):
            return subprocess.CompletedProcess(
                args=a[0], returncode=0, stdout="1.0", stderr=""
            )

        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.subprocess.run",
            _fake_run,
        )
        monkeypatch.setenv("CLAUDE_HOME", str(fake_home))
        cfg = load_config(configs_dir / "default.yaml")
        assert cfg.llm_client == "claude_cli"
        assert cfg.cli_path == "claude"

    def test_skip_cli_checks_flag(
        self, configs_dir: Path
    ) -> None:
        """skip_cli_checks=True 可跳過 CLI 檢查 (供測試)."""
        self._write_cli_cfg(configs_dir)
        cfg = load_config(
            configs_dir / "default.yaml", skip_cli_checks=True
        )
        assert cfg.llm_client == "claude_cli"


class TestTimeoutOverride:
    def test_claude_cli_timeout_seconds_env(
        self, configs_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLAUDE_CLI_TIMEOUT_SECONDS 可覆寫 config 中的值."""
        monkeypatch.setenv("CLAUDE_CLI_TIMEOUT_SECONDS", "60")
        cfg = load_config(configs_dir / "default.yaml")
        assert cfg.llm_timeout_seconds == 60.0


class TestDryRunFixture:
    def test_dry_run_missing_fixture(
        self, configs_dir: Path, tmp_path: Path
    ) -> None:
        (configs_dir / "default.yaml").write_text(
            CONFIG_YAML.replace(
                "dry_run_fixture_path: tests/fixtures/dry_run.yaml",
                "dry_run_fixture_path: nope/missing.yaml",
            ),
            encoding="utf-8",
        )
        with pytest.raises(FixtureNotFoundError):
            load_config(configs_dir / "default.yaml", dry_run=True)
