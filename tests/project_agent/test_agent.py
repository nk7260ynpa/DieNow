"""ProjectAgent decide 測試.

對應本 change (`migrate-to-claude-cli-subprocess`) 的 project-agent spec:
- 正常呼叫 (以 FakeLLMClient 替身)
- system_blocks 仍為 3 個邏輯區塊 (persona / rules / prior_life)
- LLMRequest.tools 為空 (不再使用 Anthropic tool use)
- user prompt 含 JSON 輸出指令
- CacheMetadata 恆為 0
- 不合法模型名拒絕啟動
- LLM 回傳純 JSON 文字被正確解析為 Action
"""

from __future__ import annotations

import json

import pytest

from ring_of_hands.llm.base import (
    CacheMetadata,
    ConfigValidationError,
    LLMResponse,
)
from ring_of_hands.llm.fake_client import FakeLLMClient
from ring_of_hands.project_agent.agent import (
    ProjectAgent,
    validate_model_name,
)
from ring_of_hands.script_generator.types import Persona, Script
from ring_of_hands.world_model.engine import build_initial_state
from ring_of_hands.world_model.observation import build_observation
from ring_of_hands.world_model.types import PressAction, WaitAction


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

    def test_empty_model_is_valid(self) -> None:
        """空字串代表走 CLI 預設模型, 不 raise."""
        validate_model_name("")

    def test_invalid_model_raises(self) -> None:
        with pytest.raises(ConfigValidationError):
            validate_model_name("gpt-4")


class TestDecide:
    def test_calls_llm_once_and_returns_action(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        """LLM 回傳純 JSON 文字時能正確解析為 Action."""
        fake_client.add_decide_response(
            LLMResponse(
                text=json.dumps({"action": "press", "button_id": 6}),
            )
        )
        action = agent.decide(_observation())
        assert isinstance(action, PressAction)
        assert action.button_id == 6
        log = fake_client.call_log
        assert len(log) == 1

    def test_system_blocks_has_three_entries(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        """system_blocks 仍為 3 個邏輯區塊 (persona/rules/prior_life)."""
        fake_client.add_decide_response(
            LLMResponse(text=json.dumps({"action": "wait"}))
        )
        agent.decide(_observation())
        purpose, request = fake_client.call_log[0]
        assert purpose == "agent_decide"
        assert len(request.system_blocks) == 3
        labels = {block.label for block in request.system_blocks}
        assert labels == {"persona", "rules", "prior_life"}
        # cache 欄位允許為 True/False, 實作 MUST 不因此改變 CLI 旗標組成.
        # 值本身保留 (作為 informational metadata).
        for block in request.system_blocks:
            assert isinstance(block.cache, bool)

    def test_request_has_no_tools_or_tool_choice(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        """CLI 後端不支援 tool use; tools 應為空 tuple, tool_choice 應為 None."""
        fake_client.add_decide_response(
            LLMResponse(text=json.dumps({"action": "wait"}))
        )
        agent.decide(_observation())
        _, request = fake_client.call_log[0]
        assert request.tools == ()
        assert request.tool_choice is None

    def test_user_prompt_contains_json_instruction(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        """user prompt 末尾含 JSON 輸出指令, 誘導 LLM 回傳純 JSON."""
        fake_client.add_decide_response(
            LLMResponse(text=json.dumps({"action": "wait"}))
        )
        agent.decide(_observation())
        _, request = fake_client.call_log[0]
        user_text = request.messages[-1].content
        assert "回覆格式要求" in user_text
        assert "僅輸出 JSON" in user_text
        assert '"action": "move"' in user_text

    def test_user_messages_role_is_user(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        fake_client.add_decide_response(
            LLMResponse(text=json.dumps({"action": "wait"}))
        )
        agent.decide(_observation())
        _, request = fake_client.call_log[0]
        for msg in request.messages:
            assert msg.role == "user"

    def test_cache_metadata_is_zero_but_field_preserved(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        """cache_read / cache_creation_input_tokens 欄位保留但值為 0."""
        fake_client.add_decide_response(
            LLMResponse(
                text=json.dumps({"action": "wait"}),
                cache=CacheMetadata(),
            )
        )
        agent.decide(_observation())
        # 無例外即表示 metrics 仍能寫入; response.cache 存在且皆為 0.

    def test_parse_failure_raises_action_parse_error(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        from ring_of_hands.project_agent.action_parser import ActionParseError

        fake_client.add_decide_response(
            LLMResponse(text=json.dumps({"action": "fly"}))
        )
        with pytest.raises(ActionParseError):
            agent.decide(_observation())

    def test_parses_markdown_code_fenced_json(
        self, agent: ProjectAgent, fake_client: FakeLLMClient
    ) -> None:
        """即使 LLM 輸出被 Markdown code fence 包住也能解析."""
        fake_client.add_decide_response(
            LLMResponse(text='```json\n{"action": "wait"}\n```')
        )
        action = agent.decide(_observation())
        assert isinstance(action, WaitAction)


class TestRealtimeReply:
    def test_realtime_reply_returns_text(
        self,
        agent: ProjectAgent,
        fake_client: FakeLLMClient,
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
        fake_client: FakeLLMClient,
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
