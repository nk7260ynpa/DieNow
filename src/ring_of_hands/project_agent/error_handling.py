"""Project Agent 錯誤處理的輔助型別與 helper.

主要定義已於 `agent.py` export; 本檔集中常數與 retry/熔斷邏輯給外部測試重用.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_CONSECUTIVE_FAILURE_LIMIT = 3


@dataclass
class FailureTracker:
    """LLM 連續失敗計數器.

    Attributes:
        limit: 達到此數即應 raise `LLMUnavailableError`.
        count: 當前連續失敗次數.
    """

    limit: int = DEFAULT_CONSECUTIVE_FAILURE_LIMIT
    count: int = 0

    def record_failure(self) -> int:
        """記錄一次失敗, 回傳新的 count."""
        self.count += 1
        return self.count

    def record_success(self) -> None:
        """重置計數."""
        self.count = 0

    def should_abort(self) -> bool:
        """當前是否已達中止閾值."""
        return self.count >= self.limit


__all__ = ["DEFAULT_CONSECUTIVE_FAILURE_LIMIT", "FailureTracker"]
