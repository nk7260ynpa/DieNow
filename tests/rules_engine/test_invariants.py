"""Invariants 執行期強制測試.

對應 spec Scenarios:
- INV-3 違反 raise
- INV-5 違反被自動攔截 (由 observation 建構器驗證)
- INV-7 違反: 單 tick 重覆自由 action
"""

from __future__ import annotations

import pytest

from ring_of_hands.rules_engine.invariants import check_dispatch_invariants
from ring_of_hands.world_model.engine import WorldEngine
from ring_of_hands.world_model.types import (
    InvariantViolation,
    MoveAction,
    PressAction,
)


class TestInvariants:
    def test_inv7_duplicate_free_action(self, engine: WorldEngine) -> None:
        """同 tick 內 pov_6 重覆自由 action."""
        engine.register_free_action(6)
        with pytest.raises(InvariantViolation) as exc_info:
            check_dispatch_invariants(
                engine,
                6,
                MoveAction(delta=(0, 1)),
                is_free_agent=True,
            )
        assert exc_info.value.inv_id == "INV-7"

    def test_inv4_pov6_scripted_forbidden(self, engine: WorldEngine) -> None:
        """pov_6 不得走 scripted 路徑."""
        with pytest.raises(InvariantViolation) as exc_info:
            check_dispatch_invariants(
                engine,
                6,
                MoveAction(delta=(1, 0)),
                is_free_agent=False,
            )
        assert exc_info.value.inv_id == "INV-4"

    def test_inv3_scripted_action_type_mismatch(self, engine: WorldEngine) -> None:
        """scripted pov 實際 action 與劇本 action_type 不符."""
        expected = {"action_type": "press", "payload": {"button_id": 2}, "targets": []}
        with pytest.raises(InvariantViolation) as exc_info:
            check_dispatch_invariants(
                engine,
                2,
                MoveAction(delta=(1, 0)),
                is_free_agent=False,
                expected_scripted_event=expected,
            )
        assert exc_info.value.inv_id == "INV-3"

    def test_inv8_scripted_payload_mismatch(self, engine: WorldEngine) -> None:
        """scripted 的 payload 不符."""
        expected = {"action_type": "press", "payload": {"button_id": 2}, "targets": []}
        with pytest.raises(InvariantViolation) as exc_info:
            check_dispatch_invariants(
                engine,
                2,
                PressAction(button_id=5),
                is_free_agent=False,
                expected_scripted_event=expected,
            )
        assert exc_info.value.inv_id == "INV-8"

    def test_inv3_scripted_ok(self, engine: WorldEngine) -> None:
        """scripted 一致時不 raise."""
        expected = {
            "action_type": "move",
            "payload": {"delta": [1, 0]},
            "targets": [],
        }
        # 不應 raise.
        check_dispatch_invariants(
            engine,
            2,
            MoveAction(delta=(1, 0)),
            is_free_agent=False,
            expected_scripted_event=expected,
        )
