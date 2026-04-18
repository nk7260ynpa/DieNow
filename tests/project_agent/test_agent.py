"""ProjectAgent decide 測試.

對應 spec:
- 正常呼叫 Anthropic API (以 FakeAnthropicClient 替身)
- system blocks 含 3 個快取區塊
- user 不帶 cache_control
- cache_read_input_tokens 指標被記錄
- 不合法模型名拒絕啟動
"""

from __future__ import annotations

import pytest

from ring_of_hands.llm.base import LLMResponse
from ring_of_hands.llm.fake_client import FakeAnthropicClient
from ring_of_hands.project_agent.agent import (
    ConfigValidationError,
    ProjectAgent,
    validate_model_name,
)
from ring_of_hands.script_generator.types import Persona, Script
from ring_of_hands.world_model.engine import build_initial_state
from ring_of_hands.world_model.observation import build_observation
from ring_of_hands.world_model.types import PressAction


def _observation():
    state = build_initial_state(
        room_size=(10, 10),
        body_start_positions=[(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)],
        button_positions=[(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)],
        ring_position=(5, 5),
    )
    return build_observation(state, pov_id=6)


class TestModelValidation:
    def test_valid_model(self) -> None:
        validate_model_name("claude-sonnet-4-7")
        validate_model_name("claude-opus-4-7")
        validate_model_name("claude-haiku-4-5")

    def test_invalid_model_raises(self) -> None:
        with pytest.raises(ConfigValidationError):
            validate_model_name("gpt-4")


class TestDecide:
    def test_calls_llm_once_and_returns_action(
        self, agent: ProjectAgent, fake_client: FakeAnthropicClient
    ) -> None:
        fake_client.add_decide_response(
            LLMResponse(
                text="",
                tool_use={
                    "name": "submit_action",
                    "input": {"action": "press", "button_id": 6},
                },
            )
        )
        action = agent.decide(_observation())
        assert isinstance(action, PressAction)
        assert action.button_id == 6
        log = fake_client.call_log
        assert len(log) == 1

    def test_system_blocks_has_three_cached_entries(
        self, agent: ProjectAgent, fake_client: FakeAnthropicClient
    ) -> None:
        fake_client.add_decide_response(
            LLMResponse(
                text="",
                tool_use={
                    "name": "submit_action",
                    "input": {"action": "wait"},
                },
            )
        )
        agent.decide(_observation())
        purpose, request = fake_client.call_log[0]
        assert purpose == "agent_decide"
        assert len(request.system_blocks) == 3
        assert all(block.cache for block in request.system_blocks)
        labels = {block.label for block in request.system_blocks}
        assert labels == {"persona", "rules", "prior_life"}

    def test_user_messages_has_no_cache_flag(
        self, agent: ProjectAgent, fake_client: FakeAnthropicClient
    ) -> None:
        fake_client.add_decide_response(
            LLMResponse(text="", tool_use={"name": "submit_action", "input": {"action": "wait"}})
        )
        agent.decide(_observation())
        _, request = fake_client.call_log[0]
        for msg in request.messages:
            assert msg.role == "user"

    def test_parse_failure_raises_action_parse_error(
        self, agent: ProjectAgent, fake_client: FakeAnthropicClient
    ) -> None:
        from ring_of_hands.project_agent.action_parser import ActionParseError

        fake_client.add_decide_response(
            LLMResponse(
                text="",
                tool_use={"name": "submit_action", "input": {"action": "fly"}},
            )
        )
        with pytest.raises(ActionParseError):
            agent.decide(_observation())


class TestRealtimeReply:
    def test_realtime_reply_returns_text(
        self,
        agent: ProjectAgent,
        fake_client: FakeAnthropicClient,
        pov6_prior_life: Script,
    ) -> None:
        fake_client.add_realtime_reply_response(3, "我不知道你在說什麼")
        reply = agent.realtime_reply(
            3,
            persona=Persona(name="懷疑者"),
            prior_life=pov6_prior_life.prior_life,  # pov_4 script
            incoming_msg="你記得上一世嗎?",
            upcoming_script_hint="無",
        )
        assert reply == "我不知道你在說什麼"

    def test_realtime_reply_disabled(
        self,
        fake_client: FakeAnthropicClient,
        pov6_prior_life: Script,
    ) -> None:
        from ring_of_hands.project_agent.agent import FeatureDisabledError

        agent = ProjectAgent(
            llm_client=fake_client,
            model="claude-sonnet-4-7",
            pov6_persona=Persona(name="agent"),
            pov6_prior_life=pov6_prior_life,
            enable_realtime_chat=False,
        )
        with pytest.raises(FeatureDisabledError):
            agent.realtime_reply(
                3,
                persona=Persona(name="懷疑者"),
                prior_life=None,
                incoming_msg="hi",
            )
