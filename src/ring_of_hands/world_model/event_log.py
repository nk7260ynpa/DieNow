"""Event Log append-only JSONL writer.

每一行為一個 Pydantic `Event` 的 JSON 序列化 (`model_dump_json`); 符合 INV-6
(所有 event 皆 append-only 寫入 `EventLog`). 由 `WorldEngine` 內部持有, 外部
不直接改寫檔案內容.
"""

from __future__ import annotations

import json
from io import TextIOBase
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ring_of_hands.world_model.types import Event


class EventLog:
    """JSONL event log.

    初始化時開啟檔案以 append 模式; `append(event)` 寫入一行 JSON 並立即
    flush. `close()` 關閉底層檔案. 外部不應直接讀寫檔案本身.

    Attributes:
        path: 檔案路徑. 若為 `None` 代表只存於記憶體 (測試用).
    """

    def __init__(self, path: Path | str | None = None) -> None:
        """建立 event log.

        Args:
            path: JSONL 檔案路徑. 若為 `None` 則僅將 event 記錄在記憶體
                `in_memory_events`, 不寫檔; 主要用於單元測試.
        """
        self._in_memory: list[dict] = []
        self.path: Path | None = Path(path) if path is not None else None
        self._file: TextIOBase | None = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("a", encoding="utf-8")
        self._closed = False

    def append(self, event: "Event") -> None:
        """追加一筆事件至 log.

        Args:
            event: Pydantic `Event` 物件; 會被序列化為 JSON.

        Raises:
            RuntimeError: 若 log 已關閉.
        """
        if self._closed:
            raise RuntimeError("EventLog 已關閉, 無法再寫入.")
        # 使用 model_dump_json 以保留 Literal / tuple 序列化格式.
        line = event.model_dump_json()
        # 同步記錄在記憶體, 供測試直接檢視.
        self._in_memory.append(json.loads(line))
        if self._file is not None:
            self._file.write(line)
            self._file.write("\n")
            self._file.flush()

    @property
    def in_memory_events(self) -> list[dict]:
        """回傳已記錄事件的 list (dict 格式). 主要用於測試."""
        return list(self._in_memory)

    def close(self) -> None:
        """關閉 log 檔案."""
        if self._closed:
            return
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
        self._closed = True

    def __enter__(self) -> "EventLog":
        """Context manager 進入."""
        return self

    def __exit__(self, *_: object) -> None:
        """Context manager 離開, 關閉 log."""
        self.close()


__all__ = ["EventLog"]
