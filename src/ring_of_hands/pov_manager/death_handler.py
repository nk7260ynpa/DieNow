"""死亡事件訂閱.

本模組為 `tasks.md` 6.5 指定的檔案; 邏輯實作於 `manager.PovManager.
handle_death` 與 `sync_alive_flags`, 此檔提供 thin wrapper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ring_of_hands.pov_manager.manager import PovManager


def on_death_event(manager: "PovManager", pov_id: int) -> None:
    """thin wrapper: 通知 manager 某 pov 已死亡."""
    manager.handle_death(pov_id)


def resync(manager: "PovManager") -> None:
    """thin wrapper: 依 world state 重新同步 is_alive 標記."""
    manager.sync_alive_flags()


__all__ = ["on_death_event", "resync"]
