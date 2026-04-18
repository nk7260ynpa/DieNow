"""時間一致性驗證器.

對照 `script_n` 與 `script_{n-1}` (即 prior_life), 確認共有事件完全一致.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ring_of_hands.script_generator.types import Script, ScriptEvent


class ValidationResult(BaseModel):
    """驗證結果."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    diff: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    message: str = ""


def _event_key(event: ScriptEvent) -> tuple[int, int, str]:
    """用於對齊比對的 key: (t, actor, action_type)."""
    return (event.t, event.actor, event.action_type)


def _payload_normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """將 list/tuple 正規化為 list 以利比較."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            out[key] = list(value)
        else:
            out[key] = value
    return out


def _events_conflict(prior: ScriptEvent, current: ScriptEvent) -> list[dict[str, Any]]:
    """比較 key 相同時的 payload / targets 一致性."""
    diffs: list[dict[str, Any]] = []
    prior_payload = _payload_normalize(prior.payload)
    current_payload = _payload_normalize(current.payload)
    if prior_payload != current_payload:
        diffs.append(
            {
                "t": prior.t,
                "actor": prior.actor,
                "field": "payload",
                "prior": prior_payload,
                "current": current_payload,
            }
        )
    if list(prior.targets) != list(current.targets):
        diffs.append(
            {
                "t": prior.t,
                "actor": prior.actor,
                "field": "targets",
                "prior": list(prior.targets),
                "current": list(current.targets),
            }
        )
    return diffs


def validate_closure(
    *,
    current: Script,
    prior: Script | None,
) -> ValidationResult:
    """驗證 `current` 與其 `prior_life` 的閉環一致性.

    規則:
    - 若 `prior is None` (即 current.pov_id==1), 驗證結果永遠 valid.
    - 否則, 找出 current.events 中所有「涉及 pov_{n-1}」的事件
      (actor == n-1 或 n-1 in targets), 與 prior.events 對照.
    - 同樣地, 找出 prior.events 中涉及 pov_n (current.pov_id) 的事件,
      與 current.events 對照.
    - 對齊使用 (t, actor, action_type) 為 key; 若 key 對不上則視為缺失.

    Returns:
        `ValidationResult(valid=True/False, diff=[...])`.
    """
    if prior is None:
        return ValidationResult(valid=True, message="pov_1 無前世, 自動通過.")

    prior_pov_id = prior.pov_id
    current_pov_id = current.pov_id
    diffs: list[dict[str, Any]] = []

    # 1. current 中涉及 prior 的事件 MUST 存在於 prior 且一致.
    current_events_about_prior = [
        e
        for e in current.events
        if e.actor == prior_pov_id or prior_pov_id in e.targets
    ]
    prior_event_map: dict[tuple[int, int, str], ScriptEvent] = {
        _event_key(e): e for e in prior.events
    }
    for e in current_events_about_prior:
        key = _event_key(e)
        if key not in prior_event_map:
            diffs.append(
                {
                    "t": e.t,
                    "actor": e.actor,
                    "direction": "current_missing_in_prior",
                    "event": e.model_dump(mode="json"),
                }
            )
            continue
        diffs.extend(_events_conflict(prior_event_map[key], e))

    # 2. prior 中涉及 current 的事件 MUST 存在於 current 且一致.
    prior_events_about_current = [
        e
        for e in prior.events
        if e.actor == current_pov_id or current_pov_id in e.targets
    ]
    current_event_map: dict[tuple[int, int, str], ScriptEvent] = {
        _event_key(e): e for e in current.events
    }
    for e in prior_events_about_current:
        key = _event_key(e)
        if key not in current_event_map:
            diffs.append(
                {
                    "t": e.t,
                    "actor": e.actor,
                    "direction": "prior_missing_in_current",
                    "event": e.model_dump(mode="json"),
                }
            )
            continue
        # reverse direction conflict already checked when we iterate current side
        # but ensure at least symmetric coverage.
        diffs.extend(_events_conflict(e, current_event_map[key]))

    # 去重.
    seen: set[str] = set()
    unique_diffs: list[dict[str, Any]] = []
    for d in diffs:
        key = repr(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            unique_diffs.append(d)

    return ValidationResult(
        valid=not unique_diffs,
        diff=tuple(unique_diffs),
        message=(
            "閉環一致" if not unique_diffs else f"{len(unique_diffs)} 筆不一致"
        ),
    )


__all__ = ["ValidationResult", "validate_closure"]
