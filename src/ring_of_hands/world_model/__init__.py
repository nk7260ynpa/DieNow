"""World Model capability.

集中持有關卡世界狀態並提供唯一的 observe/dispatch 介面. 外部模組 (pov-manager,
rules-engine, scenario-runner) MUST 透過本 capability 讀寫世界.
"""

from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.event_log import EventLog
from ring_of_hands.world_model.observation import build_observation
from ring_of_hands.world_model.types import (
    ActionRejectedEvent,
    Body,
    BodyStatus,
    Button,
    ButtonLitEvent,
    Coord,
    DeathEvent,
    Event,
    InvariantViolationEvent,
    MoveAction,
    MoveEvent,
    Observation,
    ObserveAction,
    Outcome,
    OutcomeEvent,
    OutcomeResult,
    PressAction,
    Ring,
    ShieldOpenEvent,
    SpeakAction,
    SpeakEvent,
    TouchRingAction,
    WaitAction,
    WorldState,
)

__all__ = [
    "ActionRejectedEvent",
    "Body",
    "BodyStatus",
    "Button",
    "ButtonLitEvent",
    "Coord",
    "DeathEvent",
    "Event",
    "EventLog",
    "InvariantViolationEvent",
    "MoveAction",
    "MoveEvent",
    "Observation",
    "ObserveAction",
    "Outcome",
    "OutcomeEvent",
    "OutcomeResult",
    "PressAction",
    "Ring",
    "ShieldOpenEvent",
    "SpeakAction",
    "SpeakEvent",
    "TouchRingAction",
    "WaitAction",
    "WorldEngine",
    "WorldState",
    "build_observation",
]
