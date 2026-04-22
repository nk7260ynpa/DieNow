"""`_parse_ndjson` 邊界與容錯測試 (design D-2, D-7).

此模組獨立於 `test_claude_cli_client.py`, 專注於 stdout NDJSON 解析層的
行為, 確保 CLI 格式微幅變動 (新增 event type, 多筆 assistant message) 時
實作仍可產出正確 `LLMResponse` 或明確的 `LLMCallFailedError`.
"""

from __future__ import annotations

import logging

import pytest

from ring_of_hands.llm.base import LLMCallFailedError
from ring_of_hands.llm.claude_cli_client import _parse_ndjson


class TestNdjsonHappyPath:
    def test_single_result_event_minimal(self) -> None:
        stdout = '{"type":"result","subtype":"success","result":"final"}\n'
        resp = _parse_ndjson(stdout)
        assert resp.text == "final"
        assert resp.tool_use is None
        assert resp.cache.cache_read_input_tokens == 0

    def test_multiple_assistant_events_before_result(self) -> None:
        """CLI 可能先 stream 多則 assistant, 最後才 result."""
        stdout = (
            '{"type":"system","subtype":"init","session":"s1"}\n'
            '{"type":"assistant","message":{"content":[{"type":"text","text":"thinking..."}]}}\n'
            '{"type":"assistant","message":{"content":[{"type":"text","text":"more..."}]}}\n'
            '{"type":"result","subtype":"success","result":"最終答案"}\n'
        )
        resp = _parse_ndjson(stdout)
        assert resp.text == "最終答案"
        assert resp.raw["stdout_events_count"] == 4

    def test_multiple_result_events_take_last(self) -> None:
        stdout = (
            '{"type":"result","subtype":"partial","result":"first"}\n'
            '{"type":"result","subtype":"success","result":"second"}\n'
        )
        resp = _parse_ndjson(stdout)
        assert resp.text == "second"


class TestNdjsonErrorCases:
    def test_no_result_event_raises(self) -> None:
        stdout = (
            '{"type":"system","subtype":"init"}\n'
            '{"type":"assistant","message":{"content":[]}}\n'
        )
        with pytest.raises(LLMCallFailedError) as excinfo:
            _parse_ndjson(stdout)
        assert excinfo.value.reason == "no_result_event"

    def test_error_event_raises_with_reason(self) -> None:
        stdout = '{"type":"error","error":{"message":"model unavailable"}}\n'
        with pytest.raises(LLMCallFailedError) as excinfo:
            _parse_ndjson(stdout)
        assert excinfo.value.reason.startswith("cli_error:")
        assert "model unavailable" in excinfo.value.reason

    def test_error_event_with_string_payload(self) -> None:
        stdout = '{"type":"error","error":"rate_limit_exceeded"}\n'
        with pytest.raises(LLMCallFailedError) as excinfo:
            _parse_ndjson(stdout)
        assert "rate_limit_exceeded" in excinfo.value.reason

    def test_result_missing_text_raises(self) -> None:
        stdout = '{"type":"result","subtype":"success"}\n'
        with pytest.raises(LLMCallFailedError) as excinfo:
            _parse_ndjson(stdout)
        assert excinfo.value.reason == "result_missing_text"

    def test_empty_stdout_raises(self) -> None:
        with pytest.raises(LLMCallFailedError) as excinfo:
            _parse_ndjson("")
        assert excinfo.value.reason == "ndjson_parse_error"

    def test_all_lines_invalid_raises_parse_error(self) -> None:
        stdout = "not json\nalso not json\n{broken\n"
        with pytest.raises(LLMCallFailedError) as excinfo:
            _parse_ndjson(stdout)
        assert excinfo.value.reason == "ndjson_parse_error"


class TestNdjsonTolerance:
    def test_unparseable_lines_are_ignored(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """無法解析的行應記 warning 並忽略, 不影響整體成功."""
        caplog.set_level(logging.WARNING)
        stdout = (
            "not a json line\n"
            '{"type":"result","subtype":"success","result":"ok"}\n'
            "trailing garbage\n"
        )
        resp = _parse_ndjson(stdout)
        assert resp.text == "ok"
        assert any("無法解析 NDJSON" in rec.message for rec in caplog.records)

    def test_non_object_json_lines_ignored(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        stdout = (
            "123\n"
            '"string line"\n'
            '[1,2]\n'
            '{"type":"result","subtype":"success","result":"y"}\n'
        )
        resp = _parse_ndjson(stdout)
        assert resp.text == "y"

    def test_blank_lines_ignored(self) -> None:
        stdout = (
            "\n"
            "   \n"
            '{"type":"result","subtype":"success","result":"ok"}\n'
            "\n"
        )
        resp = _parse_ndjson(stdout)
        assert resp.text == "ok"
