"""關卡 summary 結算."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ring_of_hands.world_model.types import Outcome


class ScenarioSummary(BaseModel):
    """關卡執行後的結算摘要."""

    model_config = ConfigDict(frozen=True)

    outcome: Outcome
    total_ticks: int
    alive_bodies_at_end: int
    lit_buttons_at_end: int
    llm_call_count: int = 0
    llm_total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    execution_duration_seconds: float = 0.0
    event_log_path: str | None = None
    run_log_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        """序列化為 JSON 字串."""
        return self.model_dump_json(indent=2)


def write_summary_file(summary: ScenarioSummary, path: Path) -> None:
    """將 summary 寫入指定 JSON 檔."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary.to_json() + "\n", encoding="utf-8")


def build_summary(
    *,
    outcome: Outcome,
    total_ticks: int,
    alive_bodies_at_end: int,
    lit_buttons_at_end: int,
    metrics: dict[str, Any],
    event_log_path: str | None = None,
    run_log_path: str | None = None,
    execution_duration_seconds: float = 0.0,
) -> ScenarioSummary:
    return ScenarioSummary(
        outcome=outcome,
        total_ticks=total_ticks,
        alive_bodies_at_end=alive_bodies_at_end,
        lit_buttons_at_end=lit_buttons_at_end,
        llm_call_count=int(metrics.get("llm_call_count", 0)),
        llm_total_tokens=int(metrics.get("llm_total_tokens", 0)),
        cache_read_tokens=int(metrics.get("cache_read_tokens", 0)),
        cache_creation_tokens=int(metrics.get("cache_creation_tokens", 0)),
        execution_duration_seconds=float(execution_duration_seconds),
        event_log_path=event_log_path,
        run_log_path=run_log_path,
    )


__all__ = ["ScenarioSummary", "build_summary", "write_summary_file"]
