"""Project Agent 錯誤處理的輔助型別與 helper.

主要定義已於 `agent.py` export; 本檔集中常數、retry/熔斷邏輯與
Claude CLI 層 `LLMCallFailedError.reason` 字串清單, 供外部測試重用.

對應本 change `migrate-to-claude-cli-subprocess` 的 D-8 錯誤映射表.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DEFAULT_CONSECUTIVE_FAILURE_LIMIT = 3


# Claude CLI 層的 `LLMCallFailedError.reason` 字串; 由 `ClaudeCLIClient`
# 在對應錯誤時填入. 本 tuple 記錄所有合法 reason prefix 供下游邏輯/文件
# 引用與 monitoring 過濾. (非前綴的具體 reason 例如
# `"cli_nonzero_exit:1"`、`"cli_error:<msg>"` 會以此前綴開頭.)
CLAUDE_CLI_ERROR_REASONS: tuple[str, ...] = (
    "cli_timeout",
    "cli_nonzero_exit:",
    "cli_not_found",
    "ndjson_parse_error",
    "cli_error:",
    "no_result_event",
    "result_missing_text",
)


CliErrorReason = Literal[
    "cli_timeout",
    "cli_not_found",
    "ndjson_parse_error",
    "no_result_event",
    "result_missing_text",
]


def is_claude_cli_error_reason(reason: str) -> bool:
    """判斷某 `LLMCallFailedError.reason` 是否屬 Claude CLI 層可辨識錯誤.

    對於帶動態欄位的錯誤 (例如 `cli_nonzero_exit:1`、`cli_error:<msg>`),
    以 prefix 方式匹配.
    """
    for known in CLAUDE_CLI_ERROR_REASONS:
        if known.endswith(":"):
            if reason.startswith(known):
                return True
        elif reason == known:
            return True
    return False


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


__all__ = [
    "CLAUDE_CLI_ERROR_REASONS",
    "CliErrorReason",
    "DEFAULT_CONSECUTIVE_FAILURE_LIMIT",
    "FailureTracker",
    "is_claude_cli_error_reason",
]
