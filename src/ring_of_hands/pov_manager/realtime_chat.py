"""即時對話路由.

本模組為 `tasks.md` 6.4 指定的檔案; 邏輯實作於 `manager.PovManager.
request_realtime_reply`, 此檔提供 thin wrapper 與衝突關鍵詞檢查 helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ring_of_hands.world_model.types import SpeakAction

if TYPE_CHECKING:
    from ring_of_hands.pov_manager.manager import PovManager
    from ring_of_hands.world_model.types import Event


CONFLICT_KEYWORDS: tuple[str, ...] = ("戒指", "拿戒指", "離開", "先走")


def contains_conflict_keyword(text: str, banned: Iterable[str] = CONFLICT_KEYWORDS) -> bool:
    """判斷 text 是否含衝突關鍵詞 (供 manager 衝突檢查使用)."""
    return any(kw in text for kw in banned)


def request_reply(
    manager: "PovManager",
    target_pov_id: int,
    action: SpeakAction,
) -> list["Event"]:
    """thin wrapper: 呼叫 manager.request_realtime_reply."""
    return manager.request_realtime_reply(target_pov_id, action)


__all__ = ["CONFLICT_KEYWORDS", "contains_conflict_keyword", "request_reply"]
