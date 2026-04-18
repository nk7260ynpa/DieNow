"""CLI 測試 (`python -m ring_of_hands.cli run ...`)."""

from __future__ import annotations

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
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from ring_of_hands.cli import main

        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
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
