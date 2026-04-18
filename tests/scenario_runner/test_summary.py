"""ScenarioSummary 測試."""

from __future__ import annotations

import json
from pathlib import Path

from ring_of_hands.scenario_runner.summary import (
    build_summary,
    write_summary_file,
)
from ring_of_hands.world_model.types import Outcome


class TestSummary:
    def test_build_and_write(self, tmp_path: Path) -> None:
        summary = build_summary(
            outcome=Outcome(result="WIN", tick=32),
            total_ticks=32,
            alive_bodies_at_end=1,
            lit_buttons_at_end=6,
            metrics={
                "llm_call_count": 10,
                "llm_total_tokens": 5000,
                "cache_read_tokens": 4000,
                "cache_creation_tokens": 200,
            },
        )
        assert summary.outcome.result == "WIN"
        path = tmp_path / "summary.json"
        write_summary_file(summary, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["outcome"]["result"] == "WIN"
        assert data["lit_buttons_at_end"] == 6
