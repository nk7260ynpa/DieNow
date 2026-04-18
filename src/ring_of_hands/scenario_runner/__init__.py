"""Scenario Runner capability.

CLI 入口, config 載入, 主流程編排, logs 輸出, summary 結算.
"""

from ring_of_hands.scenario_runner.config_loader import (
    ConfigValidationError,
    FixtureNotFoundError,
    load_config,
)
from ring_of_hands.scenario_runner.runner import ScenarioRunner
from ring_of_hands.scenario_runner.summary import ScenarioSummary
from ring_of_hands.scenario_runner.types import ScenarioConfig

__all__ = [
    "ConfigValidationError",
    "FixtureNotFoundError",
    "ScenarioConfig",
    "ScenarioRunner",
    "ScenarioSummary",
    "load_config",
]
