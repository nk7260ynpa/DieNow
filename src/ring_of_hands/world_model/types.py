"""World Model 的核心 Pydantic 型別.

涵蓋:
- 座標 / Body / Button / Ring / WorldState.
- Action 家族: `MoveAction`, `PressAction`, `TouchRingAction`,
  `SpeakAction`, `WaitAction`, `ObserveAction`.
- Event 家族: 各種事件皆帶 `tick`, `event_type`, `actor`, `payload`.
- Observation / Outcome.

所有 data class 皆以 `frozen=True` 表達 immutable, 對應 INV-2 與 INV-5 的
結構保障.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- 基本型別 ---------------------------------------------------------------

Coord = tuple[int, int]
"""Grid 座標 (x, y)."""

PovId = Annotated[int, Field(ge=1, le=6)]
"""pov 編號; 合法範圍 1..6."""

ButtonId = Annotated[int, Field(ge=1, le=6)]
"""按鈕編號; 合法範圍 1..6."""


# --- Body / Button / Ring ---------------------------------------------------


BodyStatus = Literal["alive", "corpse"]


class Body(BaseModel):
    """某個 body 的當下狀態."""

    model_config = ConfigDict(frozen=True)

    body_id: PovId
    position: Coord
    hp: int = Field(ge=0, le=100)
    number_tag: int = Field(ge=1, le=6)
    status: BodyStatus = "alive"


class Button(BaseModel):
    """按鈕實體."""

    model_config = ConfigDict(frozen=True)

    button_id: ButtonId
    position: Coord
    lit: bool = False


class Ring(BaseModel):
    """攜手之戒."""

    model_config = ConfigDict(frozen=True)

    position: Coord
    touchable: bool = False
    owner: PovId | None = None


# --- WorldState -------------------------------------------------------------


class WorldState(BaseModel):
    """世界狀態聚合.

    本類別由 `WorldEngine` 內部持有; 外部唯一合法的讀取管道為
    `WorldEngine.observe()`, 唯一合法的寫入管道為 `WorldEngine.dispatch()`.
    為強制不可變性, 所有巢狀欄位皆為 `frozen=True`.
    """

    model_config = ConfigDict(frozen=True)

    tick: int = Field(ge=0, default=0)
    room_size: Coord
    bodies: tuple[Body, ...]
    buttons: tuple[Button, ...]
    ring: Ring
    shield_open: bool = False
    recent_public_speeches: tuple[dict[str, Any], ...] = ()
    # 記錄每 tick 已提交自由 action 的 pov 清單 (for INV-7 檢查).
    free_actions_this_tick: tuple[PovId, ...] = ()

    @field_validator("bodies")
    @classmethod
    def _validate_body_count(cls, value: tuple[Body, ...]) -> tuple[Body, ...]:
        """驗證 body 數量必為 6 且 body_id 為 1..6."""
        if len(value) != 6:
            raise ValueError("WorldState MUST 包含 6 個 body")
        ids = sorted(b.body_id for b in value)
        if ids != [1, 2, 3, 4, 5, 6]:
            raise ValueError("body_id MUST 為 1..6")
        return value

    @field_validator("buttons")
    @classmethod
    def _validate_button_count(cls, value: tuple[Button, ...]) -> tuple[Button, ...]:
        """驗證 button 數量必為 6 且 button_id 為 1..6."""
        if len(value) != 6:
            raise ValueError("WorldState MUST 包含 6 個 button")
        ids = sorted(b.button_id for b in value)
        if ids != [1, 2, 3, 4, 5, 6]:
            raise ValueError("button_id MUST 為 1..6")
        return value


# --- Action 家族 ------------------------------------------------------------


class _BaseAction(BaseModel):
    """Action 基底; 子類別以 Literal 區分種類."""

    model_config = ConfigDict(frozen=True)

    action: ClassVar[str]


class MoveAction(_BaseAction):
    """移動一格."""

    action: Literal["move"] = "move"
    delta: Coord


class PressAction(_BaseAction):
    """按下某按鈕."""

    action: Literal["press"] = "press"
    button_id: ButtonId


class TouchRingAction(_BaseAction):
    """觸碰戒指."""

    action: Literal["touch_ring"] = "touch_ring"


class SpeakAction(_BaseAction):
    """說話 / 廣播."""

    action: Literal["speak"] = "speak"
    msg: str = Field(min_length=0)
    targets: tuple[PovId, ...] = ()


class WaitAction(_BaseAction):
    """停留不動."""

    action: Literal["wait"] = "wait"


class ObserveAction(_BaseAction):
    """僅觀察, 不改變世界."""

    action: Literal["observe"] = "observe"


Action = (
    MoveAction
    | PressAction
    | TouchRingAction
    | SpeakAction
    | WaitAction
    | ObserveAction
)


# --- Event 家族 -------------------------------------------------------------


class _BaseEvent(BaseModel):
    """Event 基底."""

    model_config = ConfigDict(frozen=True)

    tick: int = Field(ge=0)
    event_type: ClassVar[str]
    actor: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class MoveEvent(_BaseEvent):
    """移動事件."""

    event_type: Literal["move"] = "move"


class PressEvent(_BaseEvent):
    """按下按鈕 (不論對錯) 之事件."""

    event_type: Literal["press"] = "press"


class ButtonLitEvent(_BaseEvent):
    """某按鈕亮起."""

    event_type: Literal["button_lit"] = "button_lit"


class DeathEvent(_BaseEvent):
    """某 body 死亡."""

    event_type: Literal["death"] = "death"


class SpeakEvent(_BaseEvent):
    """說話事件."""

    event_type: Literal["speak"] = "speak"


class ShieldOpenEvent(_BaseEvent):
    """防護窗開啟."""

    event_type: Literal["shield_open"] = "shield_open"


class ActionRejectedEvent(_BaseEvent):
    """動作被拒絕."""

    event_type: Literal["action_rejected"] = "action_rejected"


class ActionDowngradedEvent(_BaseEvent):
    """動作被降級 (例如 speak 衝突降級, 或 LLM parse error 降級為 wait)."""

    event_type: Literal["action_downgraded"] = "action_downgraded"


class InvariantViolationEvent(_BaseEvent):
    """Invariant 被違反."""

    event_type: Literal["invariant_violation"] = "invariant_violation"


OutcomeResult = Literal["WIN", "FAIL"]


class OutcomeEvent(_BaseEvent):
    """終局事件."""

    event_type: Literal["outcome"] = "outcome"


class ScriptGenerationFailedEvent(_BaseEvent):
    """Script 生成失敗."""

    event_type: Literal["script_generation_failed"] = "script_generation_failed"


class MetricsEvent(_BaseEvent):
    """LLM 用量指標."""

    event_type: Literal["metrics"] = "metrics"


Event = (
    MoveEvent
    | PressEvent
    | ButtonLitEvent
    | DeathEvent
    | SpeakEvent
    | ShieldOpenEvent
    | ActionRejectedEvent
    | ActionDowngradedEvent
    | InvariantViolationEvent
    | OutcomeEvent
    | ScriptGenerationFailedEvent
    | MetricsEvent
)


# --- Observation ------------------------------------------------------------


class BodySnapshot(BaseModel):
    """observation 中其他 body 的公開摘要."""

    model_config = ConfigDict(frozen=True)

    body_id: PovId
    position: Coord
    number_tag: int
    status: BodyStatus


class Observation(BaseModel):
    """單一 pov 的可見資訊.

    重要: `self_number_tag`, 關卡規則, 通關條件 MUST NOT 在此結構中出現 (INV-5).
    """

    model_config = ConfigDict(frozen=True)

    tick: int = Field(ge=0)
    pov_id: PovId
    self_position: Coord
    self_hp: int
    self_prior_life_summary: str | None = None
    shield_open: bool
    other_bodies: tuple[BodySnapshot, ...]
    recent_public_speeches: tuple[dict[str, Any], ...] = ()
    available_actions: tuple[str, ...] = ("move", "press", "touch_ring", "speak", "wait", "observe")


# --- Outcome ----------------------------------------------------------------


class Outcome(BaseModel):
    """終局結果."""

    model_config = ConfigDict(frozen=True)

    result: OutcomeResult
    cause: str | None = None
    tick: int = Field(ge=0)


# --- 例外 -------------------------------------------------------------------


class IllegalStateTransition(Exception):
    """嘗試不合法的狀態轉移 (例如 corpse→alive)."""


class InvariantViolation(Exception):
    """Invariant 違反例外.

    Attributes:
        inv_id: 被違反的 invariant 編號 (例如 "INV-3").
        detail: 人類可讀描述.
    """

    def __init__(self, inv_id: str, detail: str) -> None:
        super().__init__(f"[{inv_id}] {detail}")
        self.inv_id = inv_id
        self.detail = detail


class CausalViolation(InvariantViolation):
    """INV-8 專用: scripted 行為與現實衝突."""

    def __init__(self, detail: str) -> None:
        super().__init__(inv_id="INV-8", detail=detail)


__all__ = [
    "Action",
    "ActionDowngradedEvent",
    "ActionRejectedEvent",
    "Body",
    "BodySnapshot",
    "BodyStatus",
    "Button",
    "ButtonId",
    "ButtonLitEvent",
    "CausalViolation",
    "Coord",
    "DeathEvent",
    "Event",
    "IllegalStateTransition",
    "InvariantViolation",
    "InvariantViolationEvent",
    "MetricsEvent",
    "MoveAction",
    "MoveEvent",
    "Observation",
    "ObserveAction",
    "Outcome",
    "OutcomeEvent",
    "OutcomeResult",
    "PovId",
    "PressAction",
    "PressEvent",
    "Ring",
    "ScriptGenerationFailedEvent",
    "ShieldOpenEvent",
    "SpeakAction",
    "SpeakEvent",
    "TouchRingAction",
    "WaitAction",
    "WorldState",
]
