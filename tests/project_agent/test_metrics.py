"""metrics.py 測試."""

from __future__ import annotations

import structlog

from ring_of_hands.llm.base import CacheMetadata, LLMResponse
from ring_of_hands.project_agent.metrics import log_llm_metrics


def test_log_llm_metrics_emits_event() -> None:
    """log_llm_metrics 不應 raise 且 structlog 可被呼叫."""
    response = LLMResponse(
        text="ok",
        cache=CacheMetadata(cache_read_input_tokens=100, cache_creation_input_tokens=50),
        usage={"input_tokens": 1, "output_tokens": 2},
    )
    # 使用 structlog testing 捕獲 log output.
    structlog.reset_defaults()
    log_llm_metrics(response, kind="decide", tick=5)
