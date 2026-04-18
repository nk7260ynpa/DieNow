"""ScenarioConfig / WorldConfig 測試."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ring_of_hands.scenario_runner.types import ScenarioConfig, WorldConfig
from ring_of_hands.script_generator.types import Persona


def _world(**override):
    data = dict(
        room_size=(10, 10),
        body_start_positions=tuple((i, i) for i in range(6)),
        button_positions=tuple((i + 2, i + 2) for i in range(6)),
        ring_position=(5, 5),
    )
    data.update(override)
    return WorldConfig(**data)


def _personas() -> tuple[Persona, ...]:
    return tuple(Persona(name=f"p{i}") for i in range(1, 6))


class TestScenarioConfig:
    def test_defaults(self) -> None:
        cfg = ScenarioConfig(
            world=_world(),
            pov1_to_5_personas=_personas(),
            pov6_persona=Persona(name="agent"),
        )
        assert cfg.max_ticks == 50
        assert cfg.llm_client == "anthropic"
        assert cfg.dry_run is False

    def test_personas_length(self) -> None:
        with pytest.raises(ValidationError):
            ScenarioConfig(
                world=_world(),
                pov1_to_5_personas=(Persona(name="only_one"),),
                pov6_persona=Persona(name="agent"),
            )

    def test_world_requires_six_positions(self) -> None:
        with pytest.raises(ValidationError):
            _world(body_start_positions=((0, 0),))

    def test_frozen(self) -> None:
        cfg = ScenarioConfig(
            world=_world(),
            pov1_to_5_personas=_personas(),
            pov6_persona=Persona(name="agent"),
        )
        with pytest.raises(ValidationError):
            cfg.max_ticks = 100  # type: ignore[misc]
