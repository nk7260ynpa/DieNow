"""error_handling.py 與連續失敗熔斷測試."""

from __future__ import annotations

import pytest

from ring_of_hands.llm.base import LLMCallFailedError
from ring_of_hands.llm.fake_client import FakeAnthropicClient
from ring_of_hands.project_agent.agent import (
    ActionParseError,
    LLMUnavailableError,
    ProjectAgent,
)
from ring_of_hands.project_agent.error_handling import FailureTracker
from ring_of_hands.script_generator.types import Persona, Script
from ring_of_hands.world_model.engine import build_initial_state
from ring_of_hands.world_model.observation import build_observation


class TestFailureTracker:
    def test_record_increment(self) -> None:
        t = FailureTracker(limit=3)
        assert t.record_failure() == 1
        assert t.record_failure() == 2
        assert t.record_failure() == 3
        assert t.should_abort()

    def test_reset(self) -> None:
        t = FailureTracker(limit=3)
        t.record_failure()
        t.record_failure()
        t.record_success()
        assert t.count == 0
        assert not t.should_abort()


class TestAgentConsecutiveFailure:
    def _observation(self):
        state = build_initial_state(
            room_size=(10, 10),
            body_start_positions=[(1, 1), (1, 8), (4, 1), (4, 8), (8, 1), (8, 8)],
            button_positions=[(2, 2), (2, 7), (5, 2), (5, 7), (7, 2), (7, 7)],
            ring_position=(5, 5),
        )
        return build_observation(state, pov_id=6)

    def test_single_failure_raises_parse_error(
        self, pov6_prior_life: Script
    ) -> None:
        client = FakeAnthropicClient()
        client.queue_error(LLMCallFailedError("timeout"))
        agent = ProjectAgent(
            llm_client=client,
            model="claude-sonnet-4-7",
            pov6_persona=Persona(name="a"),
            pov6_prior_life=pov6_prior_life,
        )
        with pytest.raises(ActionParseError):
            agent.decide(self._observation())

    def test_three_consecutive_failures_raises_llm_unavailable(
        self, pov6_prior_life: Script
    ) -> None:
        client = FakeAnthropicClient()
        for _ in range(3):
            client.queue_error(LLMCallFailedError("timeout"))
        agent = ProjectAgent(
            llm_client=client,
            model="claude-sonnet-4-7",
            pov6_persona=Persona(name="a"),
            pov6_prior_life=pov6_prior_life,
            consecutive_failure_limit=3,
        )
        # 第 1 次 → ActionParseError.
        with pytest.raises(ActionParseError):
            agent.decide(self._observation())
        # 第 2 次 → ActionParseError.
        with pytest.raises(ActionParseError):
            agent.decide(self._observation())
        # 第 3 次 → LLMUnavailableError.
        with pytest.raises(LLMUnavailableError):
            agent.decide(self._observation())
