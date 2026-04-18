"""說話規則測試.

對應 spec Scenarios:
- 公開廣播被所有存活 pov 觀察到
- 對 pov_3 點名對話觸發即時回應
- 空訊息被拒絕
"""

from __future__ import annotations

from ring_of_hands.rules_engine.speak_rule import apply_speak
from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import SpeakAction, SpeakEvent


class TestSpeakRule:
    def test_public_broadcast(self, engine: WorldEngine) -> None:
        result = apply_speak(engine, 6, SpeakAction(msg="Hello", targets=()))
        speak_events = [e for e in result.events if e.event_type == "speak"]
        assert len(speak_events) == 1
        recent = engine.state.recent_public_speeches
        assert recent and recent[-1]["msg"] == "Hello"

    def test_realtime_hook_triggered(self, engine: WorldEngine) -> None:
        called: list[int] = []

        def hook(speaker_id: int, action: SpeakAction) -> list[SpeakEvent]:
            called.append(speaker_id)
            return [
                SpeakEvent(
                    tick=engine.state.tick,
                    actor=3,
                    payload={"msg": "我不知道", "targets": [6]},
                )
            ]

        result = apply_speak(
            engine,
            6,
            SpeakAction(msg="你記得三號的事嗎?", targets=(3,)),
            realtime_chat_hook=hook,
        )
        assert called == [6]
        # 回應事件包含在 result.events 中.
        types = [e.event_type for e in result.events]
        assert types.count("speak") == 2

    def test_hook_not_triggered_when_not_pov6(self, engine: WorldEngine) -> None:
        called: list[int] = []

        def hook(speaker_id: int, action: SpeakAction) -> list[SpeakEvent]:
            called.append(speaker_id)
            return []

        apply_speak(
            engine,
            4,
            SpeakAction(msg="hello", targets=(3,)),
            realtime_chat_hook=hook,
        )
        # 非 pov_6 發話不觸發即時對話 hook.
        assert called == []

    def test_empty_message_rejected(self, engine: WorldEngine) -> None:
        result = apply_speak(engine, 2, SpeakAction(msg="", targets=()))
        rejected = [e for e in result.events if e.event_type == "action_rejected"]
        assert rejected and rejected[0].payload.get("reason") == "empty_message"

    def test_message_too_long_rejected(self, engine: WorldEngine) -> None:
        long_msg = "x" * 600
        result = apply_speak(engine, 2, SpeakAction(msg=long_msg, targets=()))
        rejected = [e for e in result.events if e.event_type == "action_rejected"]
        assert rejected and rejected[0].payload.get("reason") == "message_too_long"
