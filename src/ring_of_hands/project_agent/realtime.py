"""Realtime reply 的輔助函式.

`ProjectAgent.realtime_reply` 的實作主體位於 `agent.py`; 本檔提供 prompt
組裝與衝突關鍵詞過濾的純函式, 便於測試.
"""

from __future__ import annotations

from typing import Iterable


DEFAULT_BANNED_KEYWORDS: tuple[str, ...] = (
    "戒指",
    "拿戒指",
    "我要去",
    "先離開",
)


def contains_banned_keyword(text: str, banned: Iterable[str] = DEFAULT_BANNED_KEYWORDS) -> bool:
    """回傳 text 是否含有 banned 關鍵詞."""
    return any(word in text for word in banned)


def sanitize_reply(text: str, banned: Iterable[str] = DEFAULT_BANNED_KEYWORDS) -> str:
    """若回覆含禁字則替換為「...」; 否則保留原字串."""
    if contains_banned_keyword(text, banned):
        return "..."
    return text


__all__ = ["DEFAULT_BANNED_KEYWORDS", "contains_banned_keyword", "sanitize_reply"]
