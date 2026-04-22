"""Script Generator 型別.

Script / ScriptEvent / Persona 皆為 immutable (frozen=True) 以滿足 INV-2.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DeathCause = Literal["press_wrong", "ring_paradox", "timeout", "other"]
ScriptActionType = Literal[
    "move",
    "speak",
    "press",
    "touch_ring",
    "observe",
    "wait",
    "die",
]


class Persona(BaseModel):
    """pov 的人格描述."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    traits: tuple[str, ...] = ()


class ScriptEvent(BaseModel):
    """劇本中的單筆事件."""

    model_config = ConfigDict(frozen=True)

    t: int = Field(ge=0)
    actor: int = Field(ge=1, le=6)
    action_type: ScriptActionType
    payload: dict[str, Any] = Field(default_factory=dict)
    targets: tuple[int, ...] = ()

    @field_validator("targets")
    @classmethod
    def _validate_targets(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        """targets 每一項需為 1..6."""
        for t in value:
            if not (1 <= t <= 6):
                raise ValueError(f"targets 中的 pov_id 必須為 1..6, 收到 {t}")
        return value


class Script(BaseModel):
    """單一 pov 的完整劇本."""

    model_config = ConfigDict(frozen=True)

    pov_id: int = Field(ge=1, le=5)
    persona: Persona
    prior_life: "Script | None" = None
    events: tuple[ScriptEvent, ...]
    death_cause: DeathCause
    llm_meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("events")
    @classmethod
    def _validate_events_sorted(cls, value: tuple[ScriptEvent, ...]) -> tuple[ScriptEvent, ...]:
        """events 必須依 t 非遞減排序且以 die 結尾."""
        if not value:
            raise ValueError("Script.events 不得為空")
        for prev, curr in zip(value, value[1:]):
            if curr.t < prev.t:
                raise ValueError("events 必須依 t 非遞減排序")
        last = value[-1]
        if last.action_type != "die":
            raise ValueError("Script.events 最後 MUST 為 actor=pov 的 die 事件")
        return value

    def model_post_init(self, _context: Any) -> None:
        """Post-init 驗證: 最後 die 事件的 actor 必為 pov_id."""
        last = self.events[-1]
        if last.actor != self.pov_id:
            raise ValueError(
                f"Script(pov_id={self.pov_id}) 最後 die 事件的 actor 必須為 {self.pov_id}"
            )


Script.model_rebuild()


class ScriptConfig(BaseModel):
    """Script 產生流程設定."""

    model_config = ConfigDict(frozen=True)

    model: str = "claude-sonnet-4-6"
    max_retries: int = 3
    max_tokens: int = 4096
    temperature: float = 0.7
    llm_timeout_seconds: float = 180.0


__all__ = [
    "DeathCause",
    "Persona",
    "Script",
    "ScriptActionType",
    "ScriptConfig",
    "ScriptEvent",
]
