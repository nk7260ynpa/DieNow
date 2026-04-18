"""realtime.py (sanitize/keywords) 單元測試."""

from __future__ import annotations

from ring_of_hands.project_agent.realtime import (
    DEFAULT_BANNED_KEYWORDS,
    contains_banned_keyword,
    sanitize_reply,
)


class TestSanitize:
    def test_banned_keyword_detected(self) -> None:
        assert contains_banned_keyword("我要去拿戒指")
        assert contains_banned_keyword("我先離開了")

    def test_safe_string_passes(self) -> None:
        assert not contains_banned_keyword("我不知道你在說什麼")

    def test_sanitize_replaces_banned(self) -> None:
        assert sanitize_reply("拿戒指嗎?") == "..."

    def test_sanitize_keeps_safe(self) -> None:
        assert sanitize_reply("我很害怕") == "我很害怕"

    def test_default_banned_list(self) -> None:
        assert "戒指" in DEFAULT_BANNED_KEYWORDS
