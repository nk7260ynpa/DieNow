"""FakeAnthropicClient 測試."""

from __future__ import annotations

from pathlib import Path

import pytest

from ring_of_hands.llm.base import (
    LLMCallFailedError,
    LLMMessage,
    LLMRequest,
    LLMSystemBlock,
)
from ring_of_hands.llm.fake_client import FakeAnthropicClient, FakeClientFixture


def _request(purpose: str, **metadata: object) -> LLMRequest:
    return LLMRequest(
        model="claude-sonnet-4-7",
        system_blocks=(LLMSystemBlock(text="persona"),),
        messages=(LLMMessage(role="user", content="hi"),),
        metadata={"purpose": purpose, **metadata},
    )


class TestFakeClient:
    def test_script_response_from_fixture(self) -> None:
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
        client = FakeAnthropicClient(fixture)
        resp = client.call(_request("script_generation", pov_id=1))
        assert resp.tool_use is not None
        assert resp.tool_use["input"]["pov_id"] == 1

    def test_script_response_missing_raises(self) -> None:
        client = FakeAnthropicClient()
        with pytest.raises(LLMCallFailedError):
            client.call(_request("script_generation", pov_id=1))

    def test_decide_response_from_fixture(self) -> None:
        fixture = FakeClientFixture(
            project_agent_actions=[
                {"action": "press", "button_id": 6},
                {"action": "wait"},
            ]
        )
        client = FakeAnthropicClient(fixture)
        resp1 = client.call(_request("agent_decide"))
        resp2 = client.call(_request("agent_decide"))
        assert resp1.tool_use is not None and resp1.tool_use["input"]["action"] == "press"
        assert resp2.tool_use is not None and resp2.tool_use["input"]["action"] == "wait"

    def test_decide_response_exhausted_returns_wait(self) -> None:
        client = FakeAnthropicClient()
        resp = client.call(_request("agent_decide"))
        assert resp.tool_use is not None
        assert resp.tool_use["input"]["action"] == "wait"

    def test_realtime_reply(self) -> None:
        fixture = FakeClientFixture(realtime_replies={"3": ["我不知道", "..."]})
        client = FakeAnthropicClient(fixture)
        resp1 = client.call(_request("realtime_reply", pov_id=3))
        resp2 = client.call(_request("realtime_reply", pov_id=3))
        resp3 = client.call(_request("realtime_reply", pov_id=3))
        assert resp1.text == "我不知道"
        assert resp2.text == "..."
        # 用盡後回 fallback.
        assert resp3.text == "..."

    def test_queue_error(self) -> None:
        client = FakeAnthropicClient()
        client.queue_error(LLMCallFailedError("timeout"))
        with pytest.raises(LLMCallFailedError):
            client.call(_request("agent_decide"))

    def test_unknown_purpose(self) -> None:
        client = FakeAnthropicClient()
        with pytest.raises(LLMCallFailedError):
            client.call(_request("unknown"))

    def test_call_log(self) -> None:
        client = FakeAnthropicClient()
        client.call(_request("agent_decide"))
        log = client.call_log
        assert len(log) == 1
        assert log[0][0] == "agent_decide"


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
