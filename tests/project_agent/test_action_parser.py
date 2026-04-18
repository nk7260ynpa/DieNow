"""Action 解析器測試.

對應 spec:
- 合法 JSON 解析成 PressAction
- 非法 JSON 觸發 ActionParseError
- JSON schema 驗證失敗 (unknown action)
"""

from __future__ import annotations

import pytest

from ring_of_hands.llm.base import CacheMetadata, LLMResponse
from ring_of_hands.project_agent.action_parser import (
    ActionParseError,
    parse_action,
    parse_action_from_response,
)
from ring_of_hands.world_model.types import (
    MoveAction,
    PressAction,
    SpeakAction,
    TouchRingAction,
    WaitAction,
)


class TestParseAction:
    def test_press(self) -> None:
        action = parse_action({"action": "press", "button_id": 6})
        assert isinstance(action, PressAction)
        assert action.button_id == 6

    def test_move_with_list_delta(self) -> None:
        action = parse_action({"action": "move", "delta": [1, 0]})
        assert isinstance(action, MoveAction)
        assert action.delta == (1, 0)

    def test_touch_ring(self) -> None:
        action = parse_action({"action": "touch_ring"})
        assert isinstance(action, TouchRingAction)

    def test_speak_targets(self) -> None:
        action = parse_action(
            {"action": "speak", "msg": "hi", "targets": [1, 2, 3]}
        )
        assert isinstance(action, SpeakAction)
        assert action.targets == (1, 2, 3)

    def test_wait(self) -> None:
        assert isinstance(parse_action({"action": "wait"}), WaitAction)

    def test_unknown_action(self) -> None:
        with pytest.raises(ActionParseError) as exc_info:
            parse_action({"action": "fly"})
        assert "unknown_action_type" in str(exc_info.value)

    def test_missing_action(self) -> None:
        with pytest.raises(ActionParseError):
            parse_action({})


class TestParseFromResponse:
    def test_from_tool_use(self) -> None:
        resp = LLMResponse(
            text="",
            tool_use={"name": "submit_action", "input": {"action": "wait"}},
        )
        action = parse_action_from_response(resp)
        assert isinstance(action, WaitAction)

    def test_from_text_json(self) -> None:
        resp = LLMResponse(text='{"action": "press", "button_id": 3}')
        action = parse_action_from_response(resp)
        assert isinstance(action, PressAction)

    def test_non_json_text_raises(self) -> None:
        resp = LLMResponse(text="I think I should press button 6")
        with pytest.raises(ActionParseError):
            parse_action_from_response(resp)

    def test_empty_response_raises(self) -> None:
        resp = LLMResponse(text="")
        with pytest.raises(ActionParseError):
            parse_action_from_response(resp)
