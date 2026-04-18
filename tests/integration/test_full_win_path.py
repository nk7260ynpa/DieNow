"""Happy path 整合測試: 透過 CLI 跑 dry_run, 結果為 WIN."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"


class TestFullWinPath:
    def test_cli_dry_run_reaches_win_with_full_event_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """以 FakeAnthropicClient + dry_run.yaml 從 CLI 層執行 happy path."""
        from ring_of_hands.cli import main

        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        log_dir = tmp_path / "logs"
        code = main(
            [
                "run",
                "--config",
                str(CONFIGS_DIR / "default.yaml"),
                "--personas",
                str(CONFIGS_DIR / "personas.yaml"),
                "--dry-run",
                "--log-dir",
                str(log_dir),
            ]
        )
        captured = capsys.readouterr()
        assert code == 0, f"non-win exit: stdout={captured.out}, stderr={captured.err}"
        assert '"result": "WIN"' in captured.out

        # 驗證 logs.
        events_files = list(log_dir.glob("events_*.jsonl"))
        summary_files = list(log_dir.glob("summary_*.json"))
        assert len(events_files) == 1
        assert len(summary_files) == 1

        # JSONL 每行必為合法 JSON.
        for line in events_files[0].read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            assert "tick" in data and "event_type" in data

        summary = json.loads(summary_files[0].read_text(encoding="utf-8"))
        assert summary["outcome"]["result"] == "WIN"
        assert summary["lit_buttons_at_end"] == 6
        assert summary["alive_bodies_at_end"] >= 1
