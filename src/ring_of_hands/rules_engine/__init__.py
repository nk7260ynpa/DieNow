"""Rules Engine capability.

集中所有判定邏輯 (按鈕、戒指、移動、對話、死亡、終局、Invariants).
對外主要介面為 `dispatch(engine, pov_id, action)` 與 `post_tick_checks(engine)`.
"""

from ring_of_hands.rules_engine.dispatcher import dispatch
from ring_of_hands.rules_engine.invariants import check_dispatch_invariants
from ring_of_hands.rules_engine.outcome import post_tick_checks

__all__ = [
    "check_dispatch_invariants",
    "dispatch",
    "post_tick_checks",
]
