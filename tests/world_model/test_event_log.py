"""EventLog 的單元測試."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ring_of_hands.world_model.event_log import EventLog
from ring_of_hands.world_model.types import ButtonLitEvent, DeathEvent


class TestEventLog:
    """EventLog 行為測試."""

    def test_in_memory_mode(self) -> None:
        """無檔案時僅記錄在記憶體."""
        log = EventLog(path=None)
        log.append(ButtonLitEvent(tick=1, actor=2, payload={"button_id": 2}))
        events = log.in_memory_events
        assert len(events) == 1
        assert events[0]["event_type"] == "button_lit"
        log.close()

    def test_writes_jsonl_file(self, tmp_path: Path) -> None:
        """每筆 event 寫一行合法 JSON."""
        path = tmp_path / "events.jsonl"
        log = EventLog(path=path)
        log.append(ButtonLitEvent(tick=1, actor=2, payload={"button_id": 2}))
        log.append(DeathEvent(tick=2, actor=4, payload={"cause": "press_wrong"}))
        log.close()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert {"tick", "event_type", "actor", "payload"}.issubset(data.keys())

    def test_close_prevents_further_append(self, tmp_path: Path) -> None:
        """關閉後再 append 應 raise."""
        path = tmp_path / "events.jsonl"
        log = EventLog(path=path)
        log.close()
        with pytest.raises(RuntimeError):
            log.append(ButtonLitEvent(tick=0, payload={}))

    def test_context_manager(self, tmp_path: Path) -> None:
        """支援 context manager."""
        path = tmp_path / "events.jsonl"
        with EventLog(path=path) as log:
            log.append(ButtonLitEvent(tick=1, payload={"button_id": 3}))
        # 離開 context 後已關閉.
        assert not path.read_text(encoding="utf-8").strip() == ""
