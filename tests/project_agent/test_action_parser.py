"""Action 解析器測試.

對應本 change (`migrate-to-claude-cli-subprocess`) 的 project-agent spec:
- LLM 回傳純 JSON 文字 → 正確解析 (主要路徑).
- LLM 回傳 Markdown code fence 包裹的 JSON → 自動去除 fence 後解析.
- 非 JSON 純文字 → ActionParseError.
- JSON schema 驗證失敗 (unknown_action) → ActionParseError.
- 舊 tool_use fixture → 向後相容可解析, 並發出 DeprecationWarning.
"""

from __future__ import annotations

import warnings

import pytest

from ring_of_hands.llm.base import LLMResponse
from ring_of_hands.project_agent.action_parser import (
    ActionParseError,
    _strip_code_fence,
    parse_action,
    parse_action_from_response,
)
from ring_of_hands.world_model.types import (
    MoveAction,
    ObserveAction,
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

    def test_observe(self) -> None:
        assert isinstance(parse_action({"action": "observe"}), ObserveAction)

    def test_unknown_action(self) -> None:
        with pytest.raises(ActionParseError) as exc_info:
            parse_action({"action": "fly"})
        assert "unknown_action_type" in str(exc_info.value)

    def test_missing_action(self) -> None:
        with pytest.raises(ActionParseError):
            parse_action({})


class TestStripCodeFence:
    def test_json_fence(self) -> None:
        text = '```json\n{"action": "wait"}\n```'
        assert _strip_code_fence(text) == '{"action": "wait"}'

    def test_bare_fence(self) -> None:
        text = '```\n{"action": "wait"}\n```'
        assert _strip_code_fence(text) == '{"action": "wait"}'

    def test_no_fence(self) -> None:
        text = '{"action": "wait"}'
        assert _strip_code_fence(text) == '{"action": "wait"}'

    def test_fence_with_surrounding_whitespace(self) -> None:
        text = '   ```json\n{"action": "wait"}\n```   '
        assert _strip_code_fence(text) == '{"action": "wait"}'


class TestParseFromResponsePureJson:
    def test_plain_json(self) -> None:
        """LLM 回傳純 JSON 文字."""
        resp = LLMResponse(text='{"action": "press", "button_id": 3}')
        action = parse_action_from_response(resp)
        assert isinstance(action, PressAction)
        assert action.button_id == 3

    def test_plain_json_with_surrounding_whitespace(self) -> None:
        resp = LLMResponse(text='   {"action": "wait"}   \n')
        action = parse_action_from_response(resp)
        assert isinstance(action, WaitAction)

    def test_markdown_code_fenced_json(self) -> None:
        """LLM 回傳 Markdown code fence 包裹的 JSON 仍可解析."""
        resp = LLMResponse(text='```json\n{"action": "wait"}\n```')
        action = parse_action_from_response(resp)
        assert isinstance(action, WaitAction)

    def test_bare_code_fenced_json(self) -> None:
        resp = LLMResponse(text='```\n{"action": "wait"}\n```')
        action = parse_action_from_response(resp)
        assert isinstance(action, WaitAction)

    def test_non_json_text_raises(self) -> None:
        """非 JSON 純文字 (描述性回覆) 觸發 ActionParseError."""
        resp = LLMResponse(text="I think I should press button 6")
        with pytest.raises(ActionParseError) as excinfo:
            parse_action_from_response(resp)
        assert "text 非合法 JSON" in str(excinfo.value)

    def test_empty_response_raises(self) -> None:
        resp = LLMResponse(text="")
        with pytest.raises(ActionParseError) as excinfo:
            parse_action_from_response(resp)
        assert "LLM 回應為空" in str(excinfo.value)

    def test_unknown_action_type_raises(self) -> None:
        """JSON schema 驗證失敗: unknown action."""
        resp = LLMResponse(text='{"action": "fly", "target": "sky"}')
        with pytest.raises(ActionParseError) as excinfo:
            parse_action_from_response(resp)
        assert "unknown_action_type: fly" in str(excinfo.value)


class TestParseFromResponseToolUseFallback:
    def test_legacy_tool_use_path_still_works(self) -> None:
        """舊 fixture 的 tool_use 路徑仍可解析 (向後相容)."""
        resp = LLMResponse(
            text="",
            tool_use={"name": "submit_action", "input": {"action": "wait"}},
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            action = parse_action_from_response(resp)
        assert isinstance(action, WaitAction)
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )

    def test_tool_use_with_text_prefers_text(self) -> None:
        """若 text 與 tool_use 共存, 優先 text (主要路徑)."""
        resp = LLMResponse(
            text='{"action": "press", "button_id": 2}',
            tool_use={"name": "submit_action", "input": {"action": "wait"}},
        )
        action = parse_action_from_response(resp)
        # 來自 text 的 press, 而非 tool_use 的 wait.
        assert isinstance(action, PressAction)
        assert action.button_id == 2

    def test_tool_use_fallback_when_text_not_json(self) -> None:
        """若 text 非 JSON 但 tool_use 存在, 仍可走 fallback."""
        resp = LLMResponse(
            text="some leading text that isn't json",
            tool_use={"name": "submit_action", "input": {"action": "wait"}},
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always", DeprecationWarning)
            action = parse_action_from_response(resp)
        assert isinstance(action, WaitAction)
