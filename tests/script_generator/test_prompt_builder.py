"""prompt_builder 測試."""

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


class TestPromptBuilder:
    def test_world_env_contains_sizes(self) -> None:
        text = _world_env()
        assert "10 x 10" in text
        assert "body_1: (1, 1)" in text
        assert "button_6: (7, 7)" in text
        assert "戒指位置" in text

    def test_persona_block(self) -> None:
        p = Persona(name="新生", description="no prior", traits=("curious",))
        text = build_persona_block(p, 1)
        assert "新生" in text
        assert "curious" in text

    def test_prior_life_block_none(self) -> None:
        text = build_prior_life_block(None)
        assert "pov_1" in text

    def test_script_request_has_three_system_blocks(self) -> None:
        req = build_script_request(
            pov_id=2,
            persona=Persona(name="追憶者"),
            prior_life=None,
            world_env_block=_world_env(),
            config=ScriptConfig(),
        )
        assert len(req.system_blocks) == 3
        for block in req.system_blocks:
            assert block.cache is True
        assert req.tools and req.tools[0].name == "produce_script"
        assert req.tool_choice == {"type": "tool", "name": "produce_script"}
        assert req.metadata["purpose"] == "script_generation"
        assert req.metadata["pov_id"] == 2

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
