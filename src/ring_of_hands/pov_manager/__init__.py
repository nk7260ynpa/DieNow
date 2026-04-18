"""POV Manager capability.

管理 6 個 pov contexts 的生命週期, 協調:
- scripted pov_1~5 的劇本執行 (按 tick dispatch).
- 自由 agent pov_6 的 observation / decide / dispatch.
- pov_6 對 pov_k<6 的即時對話路由與衝突降級.
- 根據 rules-engine 的 DeathEvent 更新 is_alive.
"""

from ring_of_hands.pov_manager.manager import PovManager
from ring_of_hands.pov_manager.types import PovContext

__all__ = ["PovContext", "PovManager"]
