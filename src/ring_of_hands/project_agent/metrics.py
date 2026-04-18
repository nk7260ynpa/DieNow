"""Project Agent 的指標紀錄輔助函式.

`agent.py._log_metrics` 背後的 structlog 呼叫以此模組暴露供重用.
"""

from __future__ import annotations

import structlog

from ring_of_hands.llm.base import LLMResponse


_logger = structlog.get_logger("project_agent.metrics")


def log_llm_metrics(response: LLMResponse, *, kind: str, tick: int | None = None) -> None:
    """輸出 cache metrics 與 usage 到 structlog."""
    _logger.info(
        "llm_call",
        kind=kind,
        tick=tick,
        cache_read_input_tokens=response.cache.cache_read_input_tokens,
        cache_creation_input_tokens=response.cache.cache_creation_input_tokens,
        usage=response.usage,
    )


__all__ = ["log_llm_metrics"]
