"""prompt_builder 測試.

對應本 change (`migrate-to-claude-cli-subprocess`) 的 script-generator spec:
- LLMRequest.tools 為空 (不再使用 Anthropic tool use).
- user prompt 末尾含 Script JSON schema 範本與「僅輸出 JSON」指示.
- system_blocks 仍為 3-block 結構.
- retry_feedback 仍能附加至 user prompt.
"""

from __future__ import annotations

from ring_of_hands.script_generator.prompt_builder import (
    build_persona_block,
    build_prior_life_block,
    build_script_request,
    build_world_environment_block,
)
from ring_of_hands.script_generator.types import Persona, ScriptConfig


def _world_env() -> str:
    return build_world_environment_block(
        room_size=(10, 10),
        body_start_positions=[(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)],
        button_positions=[(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)],
        ring_position=(5, 5),
        max_ticks=50,
    )


class TestWorldEnvBlock:
    def test_contains_sizes(self) -> None:
        text = _world_env()
        assert "10 x 10" in text
        assert "body_1: (1, 1)" in text
        assert "button_6: (7, 7)" in text
        assert "戒指位置" in text

    def test_does_not_mention_produce_script_tool(self) -> None:
        """world_env block 不應再提 Anthropic tool 名稱."""
        text = _world_env()
        assert "produce_script" not in text


class TestPersonaBlock:
    def test_basic(self) -> None:
        p = Persona(name="新生", description="no prior", traits=("curious",))
        text = build_persona_block(p, 1)
        assert "新生" in text
        assert "curious" in text


class TestPriorLifeBlock:
    def test_none(self) -> None:
        text = build_prior_life_block(None)
        assert "pov_1" in text


class TestScriptRequest:
    def test_has_three_system_blocks(self) -> None:
        req = build_script_request(
            pov_id=2,
            persona=Persona(name="追憶者"),
            prior_life=None,
            world_env_block=_world_env(),
            config=ScriptConfig(),
        )
        assert len(req.system_blocks) == 3
        labels = {block.label for block in req.system_blocks}
        assert labels == {"world_env", "persona", "prior_life"}

    def test_tools_is_empty(self) -> None:
        """CLI 後端不支援 tool use; tools 應為空 tuple, tool_choice 應為 None."""
        req = build_script_request(
            pov_id=2,
            persona=Persona(name="追憶者"),
            prior_life=None,
            world_env_block=_world_env(),
            config=ScriptConfig(),
        )
        assert req.tools == ()
        assert req.tool_choice is None

    def test_user_prompt_contains_json_schema_hint(self) -> None:
        """user prompt 應要求 LLM 輸出合法 Script JSON."""
        req = build_script_request(
            pov_id=2,
            persona=Persona(name="追憶者"),
            prior_life=None,
            world_env_block=_world_env(),
            config=ScriptConfig(),
        )
        user_text = req.messages[-1].content
        assert "僅輸出 JSON" in user_text
        assert "輸出格式要求" in user_text
        assert "pov_id" in user_text
        assert "events" in user_text
        assert "death_cause" in user_text
        assert "press_wrong|ring_paradox|timeout|other" in user_text

    def test_metadata(self) -> None:
        req = build_script_request(
            pov_id=3,
            persona=Persona(name="p3"),
            prior_life=None,
            world_env_block=_world_env(),
            config=ScriptConfig(),
        )
        assert req.metadata["purpose"] == "script_generation"
        assert req.metadata["pov_id"] == 3

    def test_retry_feedback_appended_to_user(self) -> None:
        req = build_script_request(
            pov_id=2,
            persona=Persona(name="追憶者"),
            prior_life=None,
            world_env_block=_world_env(),
            config=ScriptConfig(),
            retry_feedback="之前 diff: missing event at t=3",
        )
        user_text = req.messages[-1].content
        assert "missing event" in user_text
        # retry_feedback 在 JSON schema hint 之前.
        assert user_text.index("missing event") < user_text.index("輸出格式要求")
