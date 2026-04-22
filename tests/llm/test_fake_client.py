"""FakeLLMClient 測試.

本 change 由 `FakeAnthropicClient` 更名為 `FakeLLMClient`, 舊名保留為
向後相容 alias. Fixture 格式不變; 但 response builder 改以
`LLMResponse.text = json.dumps(...)` 承載結構化資料 (不再產生
`tool_use`).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from ring_of_hands.llm.base import (
    LLMCallFailedError,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMSystemBlock,
)
from ring_of_hands.llm.fake_client import (
    FakeAnthropicClient,  # 向後相容 alias
    FakeClientFixture,
    FakeLLMClient,
)


def _request(purpose: str, **metadata: object) -> LLMRequest:
    return LLMRequest(
        model="claude-sonnet-4-7",
        system_blocks=(LLMSystemBlock(text="persona"),),
        messages=(LLMMessage(role="user", content="hi"),),
        metadata={"purpose": purpose, **metadata},
    )


class TestFakeLLMClient:
    def test_script_response_is_json_text(self) -> None:
        fixture = FakeClientFixture(
            scripts=[
                {
                    "pov_id": 1,
                    "persona": {"name": "新生"},
                    "events": [],
                    "death_cause": "timeout",
                }
            ]
        )
        client = FakeLLMClient(fixture)
        resp = client.call(_request("script_generation", pov_id=1))
        # 沒有 tool_use; text 為 JSON 字串.
        assert resp.tool_use is None
        assert resp.text
        parsed = json.loads(resp.text)
        assert parsed["pov_id"] == 1

    def test_script_response_missing_raises(self) -> None:
        client = FakeLLMClient()
        with pytest.raises(LLMCallFailedError):
            client.call(_request("script_generation", pov_id=1))

    def test_decide_response_is_json_text(self) -> None:
        fixture = FakeClientFixture(
            project_agent_actions=[
                {"action": "press", "button_id": 6},
                {"action": "wait"},
            ]
        )
        client = FakeLLMClient(fixture)
        resp1 = client.call(_request("agent_decide"))
        resp2 = client.call(_request("agent_decide"))
        assert resp1.tool_use is None
        assert json.loads(resp1.text)["action"] == "press"
        assert json.loads(resp1.text)["button_id"] == 6
        assert json.loads(resp2.text)["action"] == "wait"

    def test_decide_response_exhausted_returns_wait(self) -> None:
        client = FakeLLMClient()
        resp = client.call(_request("agent_decide"))
        assert resp.tool_use is None
        assert json.loads(resp.text)["action"] == "wait"

    def test_realtime_reply(self) -> None:
        fixture = FakeClientFixture(realtime_replies={"3": ["我不知道", "..."]})
        client = FakeLLMClient(fixture)
        resp1 = client.call(_request("realtime_reply", pov_id=3))
        resp2 = client.call(_request("realtime_reply", pov_id=3))
        resp3 = client.call(_request("realtime_reply", pov_id=3))
        assert resp1.text == "我不知道"
        assert resp2.text == "..."
        # 用盡後回 fallback.
        assert resp3.text == "..."

    def test_queue_error(self) -> None:
        client = FakeLLMClient()
        client.queue_error(LLMCallFailedError("timeout"))
        with pytest.raises(LLMCallFailedError):
            client.call(_request("agent_decide"))

    def test_unknown_purpose(self) -> None:
        client = FakeLLMClient()
        with pytest.raises(LLMCallFailedError):
            client.call(_request("unknown"))

    def test_call_log(self) -> None:
        client = FakeLLMClient()
        client.call(_request("agent_decide"))
        log = client.call_log
        assert len(log) == 1
        assert log[0][0] == "agent_decide"

    def test_cache_metadata_is_zero(self) -> None:
        """FakeLLMClient 的 cache metadata 皆為 0 (對齊 ClaudeCLIClient)."""
        client = FakeLLMClient()
        resp = client.call(_request("agent_decide"))
        assert resp.cache.cache_read_input_tokens == 0
        assert resp.cache.cache_creation_input_tokens == 0


class TestBackwardCompatAlias:
    def test_alias_is_same_class(self) -> None:
        assert FakeAnthropicClient is FakeLLMClient

    def test_alias_usage(self) -> None:
        """舊名 `FakeAnthropicClient` 可正常建立並呼叫."""
        client = FakeAnthropicClient()
        resp = client.call(_request("agent_decide"))
        assert json.loads(resp.text)["action"] == "wait"


class TestDeprecationWarningForToolUse:
    def test_add_decide_response_with_tool_use_warns(self) -> None:
        client = FakeLLMClient()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            client.add_decide_response(
                LLMResponse(
                    text="",
                    tool_use={"name": "submit_action", "input": {"action": "wait"}},
                )
            )
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        ), [w.category for w in caught]

    def test_add_script_response_with_tool_use_warns(self) -> None:
        client = FakeLLMClient()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            client.add_script_response(
                1,
                LLMResponse(
                    text="",
                    tool_use={
                        "name": "produce_script",
                        "input": {"pov_id": 1},
                    },
                ),
            )
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        )


class TestFixtureLoader:
    def test_from_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "f.yaml"
        path.write_text(
            "scripts:\n"
            "  - pov_id: 1\n"
            "    persona: {name: '新生'}\n"
            "    events: []\n"
            "    death_cause: timeout\n",
            encoding="utf-8",
        )
        fixture = FakeClientFixture.from_yaml(path)
        assert len(fixture.scripts) == 1
        assert fixture.scripts[0]["pov_id"] == 1

    def test_from_yaml_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            FakeClientFixture.from_yaml(tmp_path / "nope.yaml")
