"""World Engine: 世界狀態的唯一事實來源.

`WorldEngine` 持有 `WorldState` 與 `EventLog`, 並提供:
- `observe(pov_id)` 回傳該 pov 的 `Observation`.
- `dispatch(pov_id, action)` 經 rules-engine 驗證後套用變更.
- `advance_tick()` 推進 tick.
- `snapshot()` 取得當前 state 的不可變複本.

外部對 state 的任何直接改寫 MUST 被攔截 (由 Pydantic `frozen=True` 保障).
Dispatch 時的具體規則由 `rules_engine` 模組提供.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ring_of_hands.world_model.event_log import EventLog
from ring_of_hands.world_model.observation import build_observation
from ring_of_hands.world_model.types import (
    Action,
    Body,
    BodyStatus,
    Button,
    InvariantViolation,
    Observation,
    Outcome,
    PovId,
    Ring,
    WorldState,
)

if TYPE_CHECKING:
    from ring_of_hands.world_model.types import Event


class DispatchResult:
    """dispatch 的回傳封裝.

    Attributes:
        state: dispatch 後的新 state.
        events: 本次 dispatch 產生的事件清單.
        outcome: 若此 action 造成終局則填入; 否則為 `None`.
    """

    __slots__ = ("events", "outcome", "state")

    def __init__(
        self,
        *,
        state: WorldState,
        events: list["Event"],
        outcome: Outcome | None = None,
    ) -> None:
        self.state = state
        self.events = events
        self.outcome = outcome


class WorldEngine:
    """世界狀態管理器 (唯一事實來源).

    建議由 `scenario_runner` 透過 `build()` 建立; 其他模組僅透過 `observe`
    與 `dispatch` 介面互動.
    """

    def __init__(
        self,
        *,
        state: WorldState,
        event_log: EventLog | None = None,
        prior_life_summaries: dict[int, str | None] | None = None,
    ) -> None:
        """建立 WorldEngine.

        Args:
            state: 初始 world state.
            event_log: 事件紀錄; 若為 `None` 會建立記憶體版本.
            prior_life_summaries: pov_id -> 前世記憶摘要. 供 `observe` 注入.
        """
        self._state: WorldState = state
        self._event_log: EventLog = event_log if event_log is not None else EventLog()
        self._prior_life_summaries: dict[int, str | None] = (
            dict(prior_life_summaries) if prior_life_summaries else {}
        )
        self._outcome: Outcome | None = None
        # Dispatcher 由 rules_engine 注入, 避免循環 import.
        self._dispatcher_fn: Any = None

    # --- 介面 --------------------------------------------------------------

    @property
    def state(self) -> WorldState:
        """回傳當前 state (frozen). 外部直接 mutation 會被 Pydantic 攔截."""
        return self._state

    @property
    def event_log(self) -> EventLog:
        """回傳 event log 參考 (append-only)."""
        return self._event_log

    @property
    def outcome(self) -> Outcome | None:
        """回傳當前終局; 若尚未分勝負則為 `None`."""
        return self._outcome

    def set_dispatcher(self, dispatcher_fn: Any) -> None:
        """注入 rules_engine 的 dispatcher 函式.

        Args:
            dispatcher_fn: callable `(engine, pov_id, action) -> DispatchResult`.
        """
        self._dispatcher_fn = dispatcher_fn

    def observe(self, pov_id: PovId) -> Observation:
        """為指定 pov 建構 observation.

        Args:
            pov_id: pov 編號 (1..6).

        Returns:
            `Observation`.
        """
        return build_observation(
            self._state,
            pov_id,
            prior_life_summary=self._prior_life_summaries.get(pov_id),
        )

    def dispatch(self, pov_id: PovId, action: Action) -> DispatchResult:
        """委託 rules-engine 處理 action.

        Args:
            pov_id: 發起 action 的 pov.
            action: 合法的 `Action` 子型別.

        Returns:
            `DispatchResult`.

        Raises:
            RuntimeError: 若 dispatcher 尚未注入.
            InvariantViolation: 若違反 invariant.
        """
        if self._dispatcher_fn is None:
            raise RuntimeError(
                "WorldEngine 尚未注入 dispatcher; 請先呼叫 set_dispatcher."
            )
        result: DispatchResult = self._dispatcher_fn(self, pov_id, action)
        self._apply_result(result)
        return result

    def advance_tick(self) -> WorldState:
        """將 tick +1 並重置「本 tick 已提交自由 action 的 pov 清單」."""
        new_state = self._state.model_copy(
            update={
                "tick": self._state.tick + 1,
                "free_actions_this_tick": (),
            }
        )
        self._state = new_state
        return self._state

    def snapshot(self) -> WorldState:
        """取得當前 state 複本 (本身即 frozen, 此方法等同直接存取)."""
        return self._state

    # --- 供 rules-engine 內部使用 ------------------------------------------

    def _apply_result(self, result: DispatchResult) -> None:
        """套用 dispatcher 產出的結果."""
        self._state = result.state
        for event in result.events:
            self._event_log.append(event)
        if result.outcome is not None:
            self._outcome = result.outcome

    def update_state(self, new_state: WorldState) -> None:
        """由 rules-engine 於內部更新 state.

        外部不應呼叫此方法; 僅供 rules-engine 於處理 tick 終局判定時使用.
        """
        self._state = new_state

    def write_event(self, event: "Event") -> None:
        """追加事件至 event log (供 rules-engine 與 runner 使用)."""
        self._event_log.append(event)

    def set_outcome(self, outcome: Outcome) -> None:
        """設定終局 (rules-engine 內部使用)."""
        self._outcome = outcome

    def register_free_action(self, pov_id: PovId) -> None:
        """登記 pov_id 於當前 tick 已提交自由 action (INV-7 追蹤)."""
        if pov_id in self._state.free_actions_this_tick:
            raise InvariantViolation(
                "INV-7",
                f"pov_{pov_id} 於 tick {self._state.tick} 重覆提交自由 action",
            )
        self._state = self._state.model_copy(
            update={
                "free_actions_this_tick": (
                    *self._state.free_actions_this_tick,
                    pov_id,
                )
            }
        )

    # --- 工具方法 ----------------------------------------------------------

    def find_body(self, body_id: PovId) -> Body:
        """取得指定 body 的當前狀態."""
        return next(b for b in self._state.bodies if b.body_id == body_id)

    def find_button(self, button_id: int) -> Button:
        """取得指定 button 的當前狀態."""
        return next(b for b in self._state.buttons if b.button_id == button_id)

    def ring(self) -> Ring:
        """當前戒指狀態."""
        return self._state.ring

    def update_body(self, body_id: PovId, **updates: Any) -> Body:
        """以新欄位覆寫 body 並回傳新 body."""
        bodies = list(self._state.bodies)
        for idx, body in enumerate(bodies):
            if body.body_id == body_id:
                new_body = body.model_copy(update=updates)
                bodies[idx] = new_body
                self._state = self._state.model_copy(update={"bodies": tuple(bodies)})
                return new_body
        raise KeyError(f"body_{body_id} 不存在")

    def update_button(self, button_id: int, **updates: Any) -> Button:
        """以新欄位覆寫 button 並回傳新 button."""
        buttons = list(self._state.buttons)
        for idx, button in enumerate(buttons):
            if button.button_id == button_id:
                new_button = button.model_copy(update=updates)
                buttons[idx] = new_button
                self._state = self._state.model_copy(
                    update={"buttons": tuple(buttons)}
                )
                return new_button
        raise KeyError(f"button_{button_id} 不存在")

    def update_ring(self, **updates: Any) -> Ring:
        """以新欄位覆寫 ring."""
        new_ring = self._state.ring.model_copy(update=updates)
        self._state = self._state.model_copy(update={"ring": new_ring})
        return new_ring

    def set_shield_open(self, value: bool) -> None:
        """設定防護窗狀態."""
        self._state = self._state.model_copy(update={"shield_open": value})

    def append_public_speech(self, entry: dict) -> None:
        """將一則公開發言追加至最近公開發言清單 (保留最後 20 則)."""
        new_speeches = (*self._state.recent_public_speeches, entry)[-20:]
        self._state = self._state.model_copy(
            update={"recent_public_speeches": new_speeches}
        )


def build_initial_state(
    *,
    room_size: tuple[int, int],
    body_start_positions: list[tuple[int, int]],
    button_positions: list[tuple[int, int]],
    ring_position: tuple[int, int],
    body_statuses: list[BodyStatus] | None = None,
) -> WorldState:
    """以 config 建立初始 WorldState.

    Args:
        room_size: `(width, height)`.
        body_start_positions: 6 個 body 的起始位置, 索引 i 對應 body_{i+1}.
        button_positions: 6 個按鈕位置, 索引 i 對應 button_{i+1}.
        ring_position: 戒指位置.
        body_statuses: 初始 body 狀態清單 (預設全為 alive); 測試用.

    Returns:
        合法 WorldState.

    Raises:
        ValueError: 若 config 無效 (例如座標超出房間).
    """
    width, height = room_size
    if len(body_start_positions) != 6:
        raise ValueError("body_start_positions 必須為 6 筆")
    if len(button_positions) != 6:
        raise ValueError("button_positions 必須為 6 筆")
    for pos in [*body_start_positions, *button_positions, ring_position]:
        x, y = pos
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"座標 {pos} 超出房間大小 {room_size}")

    statuses = body_statuses or ["alive"] * 6
    bodies = tuple(
        Body(
            body_id=i + 1,
            position=tuple(body_start_positions[i]),
            hp=100 if statuses[i] == "alive" else 0,
            number_tag=i + 1,
            status=statuses[i],
        )
        for i in range(6)
    )
    buttons = tuple(
        Button(button_id=i + 1, position=tuple(button_positions[i]))
        for i in range(6)
    )
    ring = Ring(position=tuple(ring_position))
    return WorldState(
        tick=0,
        room_size=tuple(room_size),
        bodies=bodies,
        buttons=buttons,
        ring=ring,
        shield_open=False,
    )


__all__ = ["DispatchResult", "WorldEngine", "build_initial_state"]
