"""pov_6 自由 agent 執行器.

本模組為 `tasks.md` 6.3 指定的檔案; 邏輯實作於 `manager.PovManager.
tick_free_agent`, 此檔提供 thin wrapper 與獨立 helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ring_of_hands.world_model.types import Action, Observation, WaitAction

if TYPE_CHECKING:
    from ring_of_hands.pov_manager.manager import PovManager


def safe_decide(
    decide_fn: Callable[[int, Observation], Action],
    pov_id: int,
    observation: Observation,
) -> Action:
    """執行 decide_fn 並在失敗時降級為 WaitAction.

    Args:
        decide_fn: project-agent 的 decide 介面.
        pov_id: pov 編號 (通常為 6).
        observation: 當前 observation.

    Returns:
        合法的 Action; 若 decide_fn raise 則回傳 `WaitAction()`.
    """
    try:
        return decide_fn(pov_id, observation)
    except Exception:  # noqa: BLE001
        return WaitAction()


def run_free_agent_tick(
    manager: "PovManager", tick: int
) -> None:
    """thin wrapper: 呼叫 manager.tick_free_agent."""
    manager.tick_free_agent(tick)


__all__ = ["run_free_agent_tick", "safe_decide"]
