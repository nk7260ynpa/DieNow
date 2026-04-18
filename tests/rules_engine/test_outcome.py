"""終局判定測試.

對應 spec Scenarios:
- 必要 body 死亡且其按鈕未亮時提前宣告敗局
- 必要 body 死亡但該按鈕已先亮不算敗局
- 6 燈齊亮後戒指變可觸碰
- Timeout 觸發敗局
"""

from __future__ import annotations

from ring_of_hands.rules_engine.outcome import post_tick_checks
from ring_of_hands.world_model.engine import WorldEngine


class TestOutcome:
    def test_six_lights_open_shield(self, engine: WorldEngine) -> None:
        for i in range(1, 7):
            engine.update_button(i, lit=True)
        result = post_tick_checks(engine, max_ticks=50)
        assert result is None  # 尚未分勝負
        assert engine.state.shield_open is True
        assert engine.state.ring.touchable is True

    def test_unreachable_six_lights(self, engine: WorldEngine) -> None:
        # body_3 死亡且 button_3 未亮.
        engine.update_body(3, status="corpse", hp=0)
        result = post_tick_checks(engine, max_ticks=50)
        assert result is not None
        assert result.result == "FAIL"
        assert result.cause == "unreachable_six_lights"

    def test_unreachable_after_button_lit_ok(self, engine: WorldEngine) -> None:
        """body_3 死亡但 button_3 已先亮 → 不判 FAIL."""
        engine.update_button(3, lit=True)
        engine.update_body(3, status="corpse", hp=0)
        result = post_tick_checks(engine, max_ticks=50)
        assert result is None

    def test_timeout(self, engine: WorldEngine) -> None:
        # 推進 tick 至 50 (== max_ticks)
        for _ in range(50):
            engine.advance_tick()
        assert engine.state.tick == 50
        result = post_tick_checks(engine, max_ticks=50)
        assert result is not None
        assert result.result == "FAIL"
        assert result.cause == "timeout"
