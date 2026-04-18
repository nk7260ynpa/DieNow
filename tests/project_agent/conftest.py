"""project_agent 共用 fixture."""

from __future__ import annotations

import pytest

from ring_of_hands.llm.fake_client import FakeAnthropicClient
from ring_of_hands.project_agent.agent import ProjectAgent
from ring_of_hands.script_generator.types import Persona, Script, ScriptEvent


@pytest.fixture
def pov6_prior_life() -> Script:
    """建構一份可當作 pov_6 prior_life 的 script_5."""
    prior: Script | None = None
    for i in range(1, 6):
        s = Script(
            pov_id=i,
            persona=Persona(name=f"pov_{i}"),
            prior_life=prior,
            events=(
                ScriptEvent(
                    t=1, actor=i, action_type="wait", payload={}
                ),
                ScriptEvent(
                    t=10,
                    actor=i,
                    action_type="die",
                    payload={"cause": "timeout"},
                ),
            ),
            death_cause="timeout",
        )
        prior = s
    assert prior is not None
    return prior


@pytest.fixture
def fake_client() -> FakeAnthropicClient:
    return FakeAnthropicClient()


@pytest.fixture
def agent(
    fake_client: FakeAnthropicClient, pov6_prior_life: Script
) -> ProjectAgent:
    return ProjectAgent(
        llm_client=fake_client,
        model="claude-sonnet-4-7",
        pov6_persona=Persona(name="被困的玩家", description="dumb"),
        pov6_prior_life=pov6_prior_life,
    )
