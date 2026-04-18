"""終局判定.

對應 specs/rules-engine/spec.md "終局判定".
包含:
- 6 燈齊亮 → 開防護窗
- 必要 body 死亡且其按鈕未亮 → FAIL(unreachable_six_lights)
- tick >= max_ticks → FAIL(timeout)
"""

from __future__ import annotations

from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import (
    Outcome,
    OutcomeEvent,
    ShieldOpenEvent,
)


def post_tick_checks(engine: WorldEngine, *, max_ticks: int) -> Outcome | None:
    """tick 結束後的終局與派生狀態判定.

    Args:
        engine: WorldEngine.
        max_ticks: 配置的最大 tick 數.

    Returns:
        若已判定終局則回傳 `Outcome`, 否則 `None`.
    """
    if engine.outcome is not None:
        return engine.outcome

    state = engine.state
    tick = state.tick
    lit_count = sum(1 for b in state.buttons if b.lit)

    # 6 燈齊亮 → 開防護窗 + ring 可觸碰.
    if lit_count == 6 and not state.shield_open:
        engine.set_shield_open(True)
        engine.update_ring(touchable=True)
        engine.write_event(
            ShieldOpenEvent(
                tick=tick,
                actor=None,
                payload={},
            )
        )

    # unreachable_six_lights: 若任何 button 未亮, 且該 button 對應的 body 已死,
    # 則再也無法湊齊 6 燈.
    unreachable = False
    for button in state.buttons:
        if button.lit:
            continue
        body = engine.find_body(button.button_id)
        if body.status != "alive":
            unreachable = True
            break
    if unreachable:
        outcome = Outcome(result="FAIL", cause="unreachable_six_lights", tick=tick)
        engine.set_outcome(outcome)
        engine.write_event(
            OutcomeEvent(
                tick=tick,
                actor=None,
                payload={
                    "result": "FAIL",
                    "cause": "unreachable_six_lights",
                },
            )
        )
        return outcome

    # Timeout: tick >= max_ticks.
    if tick >= max_ticks:
        outcome = Outcome(result="FAIL", cause="timeout", tick=tick)
        engine.set_outcome(outcome)
        engine.write_event(
            OutcomeEvent(
                tick=tick,
                actor=None,
                payload={"result": "FAIL", "cause": "timeout"},
            )
        )
        return outcome

    return None


__all__ = ["post_tick_checks"]
