"""按鈕按壓規則測試.

對應 spec Scenarios:
- body 按下正確按鈕 → 亮燈
- body 按下錯誤按鈕立即死亡
- 距離過遠無法按壓
"""

from __future__ import annotations

from ring_of_hands.rules_engine.button_rule import apply_press
from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import PressAction


def _move_body_to(engine: WorldEngine, body_id: int, pos: tuple[int, int]) -> None:
    engine.update_body(body_id, position=pos)


class TestButtonRule:
    def test_correct_press_lights_button(self, engine: WorldEngine) -> None:
        """body_4 按對 button_4 應亮燈."""
        # body_4 起始 (4,8); button_4 位於 (5,7); 將 body_4 移至 (5,8) 以鄰接.
        _move_body_to(engine, 4, (5, 8))
        result = apply_press(engine, 4, PressAction(button_id=4))
        assert engine.find_button(4).lit is True
        assert engine.find_body(4).status == "alive"
        types = [e.event_type for e in result.events]
        assert "press" in types and "button_lit" in types

    def test_wrong_press_kills_body(self, engine: WorldEngine) -> None:
        """body_4 按錯 button_2 立即死亡."""
        # body_4 至 (2,7) 緊鄰 button_2=(2,7) 位置 (重疊 → 鄰接 distance 0).
        _move_body_to(engine, 4, (3, 7))  # 避免 body_4 踩在 button_2 上
        result = apply_press(engine, 4, PressAction(button_id=2))
        assert engine.find_body(4).status == "corpse"
        assert engine.find_button(2).lit is False
        types = [e.event_type for e in result.events]
        assert "death" in types

    def test_out_of_range_rejected(self, engine: WorldEngine) -> None:
        """距離過遠被拒絕."""
        # body_4 保持 (4,8), 距 button_4=(5,7) chebyshev=1 (rejected 需要 > 1).
        # 改將 body_4 移到 (0,0) 距 button_4=(5,7) chebyshev=7.
        _move_body_to(engine, 4, (0, 0))
        result = apply_press(engine, 4, PressAction(button_id=4))
        assert engine.find_button(4).lit is False
        assert engine.find_body(4).status == "alive"
        rejected = [e for e in result.events if e.event_type == "action_rejected"]
        assert rejected
        assert rejected[0].payload.get("reason") == "out_of_range"
