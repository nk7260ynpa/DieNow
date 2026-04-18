"""Invariants 執行期強制.

對應 specs/rules-engine/spec.md "Invariants 執行期強制".

Invariant 編號:
- INV-1: 任何 state mutation 只能經由 `WorldEngine.dispatch` / `WorldEngine`
  提供的 helper; 由型別 frozen 與 engine 封裝保障.
- INV-2: Script immutable; 由 pydantic frozen 保障.
- INV-3: scripted action 與當前 tick 的劇本條目匹配.
- INV-4: pov_6 的 action 不得觸發任何 script mutation; 由 pov-manager
  設計保障 (不暴露 mutate script 的介面).
- INV-5: observation 不得洩露自己的 number_tag/規則/目標.
- INV-6: 所有 event append-only 寫入 EventLog; 由 EventLog 保障.
- INV-7: 同一 tick 對同一 pov 僅接受 1 次自由意志 action; 由
  `WorldEngine.register_free_action` 攔截.
- INV-8: 不存在違反劇本的行為鏈 (與 INV-3 共同維護).

本檔主要提供 `check_dispatch_invariants` 於 dispatch 進行前的聚合式檢查
與 `assert_scripted_matches_event` 等工具.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ring_of_hands.world_model.types import (
    Action,
    CausalViolation,
    InvariantViolation,
    InvariantViolationEvent,
    PovId,
)

if TYPE_CHECKING:
    from ring_of_hands.world_model.engine import WorldEngine


def check_dispatch_invariants(
    engine: "WorldEngine",
    pov_id: PovId,
    action: Action,
    *,
    is_free_agent: bool,
    expected_scripted_event: dict[str, Any] | None = None,
) -> None:
    """於 dispatch 之前進行 invariant 檢查.

    Args:
        engine: WorldEngine.
        pov_id: 發起 action 的 pov.
        action: 即將 dispatch 的 action.
        is_free_agent: `True` 表示此 action 來自 pov_6 自由意志;
            `False` 表示來自 scripted pov_1~5 (由 pov-manager 劇本執行器).
        expected_scripted_event: 對 scripted pov 驗證時, 應帶入對應的
            script event 字典 (含 `action_type`, `payload`, `targets`).
            用於 INV-3 / INV-8 檢查.

    Raises:
        InvariantViolation: INV-3 / INV-4 / INV-7 / INV-8 違反.
    """
    # INV-7: 同一 tick 單一 pov 僅允許 1 次自由意志 action.
    if is_free_agent:
        if pov_id in engine.state.free_actions_this_tick:
            _record_and_raise(
                engine,
                inv_id="INV-7",
                detail=(
                    f"pov_{pov_id} 於 tick {engine.state.tick} 已提交過 "
                    "自由 action."
                ),
                actor=pov_id,
            )

    # INV-4: pov_6 本身不得被當作 scripted pov 執行.
    if not is_free_agent and pov_id == 6:
        _record_and_raise(
            engine,
            inv_id="INV-4",
            detail="pov_6 為自由主體, 不得經由 scripted 路徑 dispatch.",
            actor=pov_id,
        )

    if not is_free_agent and expected_scripted_event is not None:
        # INV-3 / INV-8: scripted action 必須與劇本 event 吻合.
        expected_action_type = expected_scripted_event.get("action_type")
        actual_action_type = action.action
        if expected_action_type != actual_action_type:
            _record_and_raise(
                engine,
                inv_id="INV-3",
                detail=(
                    f"pov_{pov_id} 於 tick {engine.state.tick} 的 scripted "
                    f"action 應為 {expected_action_type}, 實際為 "
                    f"{actual_action_type}."
                ),
                actor=pov_id,
            )
        expected_payload = expected_scripted_event.get("payload", {}) or {}
        actual_payload = _action_payload(action)
        if _normalize_payload(expected_payload) != _normalize_payload(actual_payload):
            _record_and_raise(
                engine,
                inv_id="INV-8",
                detail=(
                    f"pov_{pov_id} 於 tick {engine.state.tick} 的 scripted "
                    f"payload 與劇本不符: expected={expected_payload}, "
                    f"actual={actual_payload}"
                ),
                actor=pov_id,
            )


def assert_causal(engine: "WorldEngine", detail: str) -> None:
    """由 pov-manager 或 runner 呼叫以強制中止: scripted 行為與現實衝突.

    此為 INV-8 的明確觸發點.
    """
    event = InvariantViolationEvent(
        tick=engine.state.tick,
        actor=None,
        payload={"inv_id": "INV-8", "detail": detail},
    )
    engine.write_event(event)
    raise CausalViolation(detail)


def _action_payload(action: Action) -> dict[str, Any]:
    """從 Action 萃取出 payload 形式 (與 script event 的 payload 對齊).

    不同 action 類型的 payload 內容:
    - MoveAction: {delta: [x, y]}
    - PressAction: {button_id: n}
    - SpeakAction: {msg: ..., targets: [...]}
    - TouchRingAction: {}
    - WaitAction: {}
    - ObserveAction: {}
    """
    data = action.model_dump()
    # 將 action 的識別欄位剝除, 僅留下具體 payload 欄位.
    data.pop("action", None)
    return data


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """將 payload 中的 list/tuple 正規化以利比較."""
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            normalized[key] = list(value)
        else:
            normalized[key] = value
    return normalized


def _record_and_raise(
    engine: "WorldEngine",
    *,
    inv_id: str,
    detail: str,
    actor: int | None,
) -> None:
    engine.write_event(
        InvariantViolationEvent(
            tick=engine.state.tick,
            actor=actor,
            payload={"inv_id": inv_id, "detail": detail},
        )
    )
    raise InvariantViolation(inv_id, detail)


__all__ = [
    "assert_causal",
    "check_dispatch_invariants",
]
