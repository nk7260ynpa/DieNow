"""Scenario Runner 的設定型別."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ring_of_hands.script_generator.types import Persona


class WorldConfig(BaseModel):
    """房間幾何與物件位置."""

    model_config = ConfigDict(frozen=True)

    room_size: tuple[int, int] = (10, 10)
    body_start_positions: tuple[tuple[int, int], ...]
    button_positions: tuple[tuple[int, int], ...]
    ring_position: tuple[int, int]

    @field_validator("body_start_positions", "button_positions")
    @classmethod
    def _require_six(cls, value):
        if len(value) != 6:
            raise ValueError("需要 6 筆座標")
        return value


class ScenarioConfig(BaseModel):
    """整個關卡執行流程的設定.

    本 change (`migrate-to-claude-cli-subprocess`) 新增 CLI-backend 專屬
    欄位 `cli_path` / `claude_home`; `llm_client` 由 `"anthropic"` 改為
    `"claude_cli"` 作為生產後端的合法 literal. `anthropic_api_key` 欄位
    保留為相容欄位, 但新程式碼不再使用.
    """

    model_config = ConfigDict(frozen=True)

    world: WorldConfig
    pov1_to_5_personas: tuple[Persona, ...]
    pov6_persona: Persona

    max_ticks: int = Field(ge=1, default=50)
    max_retries: int = Field(ge=1, default=3)
    max_speak_length: int = Field(ge=1, default=512)
    enable_realtime_chat: bool = True
    llm_timeout_seconds: float = Field(gt=0.0, default=30.0)

    llm_client: Literal["claude_cli", "fake"] = "claude_cli"
    project_agent_model: str = "claude-sonnet-4-7"

    # Claude CLI 相關設定.
    cli_path: str = "claude"
    claude_home: str = "~/.claude"

    # 向後相容保留欄位; 本 change 後不再使用 Anthropic SDK.
    anthropic_api_key: str | None = None

    dry_run_fixture_path: Path = Path("tests/fixtures/dry_run.yaml")
    dry_run: bool = False

    issues_md_path: Path = Path(
        "openspec/changes/migrate-to-claude-cli-subprocess/issues.md"
    )

    @field_validator("pov1_to_5_personas")
    @classmethod
    def _require_five(cls, value: tuple[Persona, ...]) -> tuple[Persona, ...]:
        if len(value) != 5:
            raise ValueError("pov1_to_5_personas 必須為 5 筆")
        return value


__all__ = ["ScenarioConfig", "WorldConfig"]
