"""CLI 測試 (`python -m ring_of_hands.cli run ...`).

本 change (`migrate-to-claude-cli-subprocess`) 後:
- 不再需要 ANTHROPIC_API_KEY.
- 非 dry-run 模式下缺 `claude` CLI 或 `~/.claude/` 會非零退出.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"


class TestCli:
    def test_missing_config_exit_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from ring_of_hands.cli import main

        code = main(
            ["run", "--config", str(tmp_path / "no.yaml"), "--dry-run"]
        )
        assert code != 0
        captured = capsys.readouterr()
        assert "ConfigValidationError" in captured.err

    def test_dry_run_reaches_win(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from ring_of_hands.cli import main

        code = main(
            [
                "run",
                "--config",
                str(CONFIGS_DIR / "default.yaml"),
                "--personas",
                str(CONFIGS_DIR / "personas.yaml"),
                "--dry-run",
                "--log-dir",
                str(tmp_path / "logs"),
                "--log-level",
                "INFO",
            ]
        )
        captured = capsys.readouterr()
        # WIN → code == 0.
        assert code == 0, f"stdout={captured.out}\nstderr={captured.err}"
        assert '"result": "WIN"' in captured.out

    def test_claude_cli_missing_non_dry_run_exits_nonzero(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """非 dry-run 且 `claude` 不存在 → 非零退出, stderr 含安裝建議."""
        # 模擬 CLI 不存在.
        monkeypatch.setattr(
            "ring_of_hands.scenario_runner.config_loader.shutil.which",
            lambda _: None,
        )
        from ring_of_hands.cli import main

        code = main(
            [
                "run",
                "--config",
                str(CONFIGS_DIR / "default.yaml"),
                "--personas",
                str(CONFIGS_DIR / "personas.yaml"),
                "--log-dir",
                str(tmp_path / "logs"),
            ]
        )
        captured = capsys.readouterr()
        assert code != 0
        assert "ConfigValidationError" in captured.err
        assert "claude CLI 不可執行" in captured.err

    def test_claude_home_missing_non_dry_run_exits_nonzero(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """非 dry-run 且 `~/.claude/` 不存在 → 非零退出, stderr 提示 `claude login`."""
        # 模擬 CLI 存在, version 成功, 但 ~/.claude/ 不存在.
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
        monkeypatch.setenv("CLAUDE_HOME", str(tmp_path / "does-not-exist"))

        from ring_of_hands.cli import main

        code = main(
            [
                "run",
                "--config",
                str(CONFIGS_DIR / "default.yaml"),
                "--personas",
                str(CONFIGS_DIR / "personas.yaml"),
                "--log-dir",
                str(tmp_path / "logs"),
            ]
        )
        captured = capsys.readouterr()
        assert code != 0
        assert "claude login" in captured.err
