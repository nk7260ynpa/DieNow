"""metrics.py 測試.

對應本 change (`migrate-to-claude-cli-subprocess`) 的 project-agent spec:
- backend 為 ClaudeCLIClient 時 cache metrics 皆為 0, 但欄位仍存在於 log 中.
- 欄位 schema 不變 (下游 summary / event log 依賴).
"""

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
    structlog.reset_defaults()
    log_llm_metrics(response, kind="decide", tick=5)


def test_log_llm_metrics_with_zero_cache_does_not_raise() -> None:
    """CLI backend: cache_read / cache_creation 皆為 0 時仍能記錄.

    確保欄位 schema 對下游穩定 (summary / run log / event log).
    """
    response = LLMResponse(
        text=r'{"action":"wait"}',
        cache=CacheMetadata(cache_read_input_tokens=0, cache_creation_input_tokens=0),
        usage={"input_tokens": 500, "output_tokens": 20},
    )
    structlog.reset_defaults()
    # 多次呼叫不同 kind; 皆不應 raise.
    log_llm_metrics(response, kind="decide", tick=1)
    log_llm_metrics(response, kind="realtime", tick=2)
    log_llm_metrics(response, kind="script_generation", tick=None)


def test_log_llm_metrics_structured_fields_include_cache_metadata() -> None:
    """使用 structlog testing utilities 驗證欄位存在."""
    from structlog.testing import capture_logs

    response = LLMResponse(
        text="",
        cache=CacheMetadata(cache_read_input_tokens=0, cache_creation_input_tokens=0),
        usage={"input_tokens": 123},
    )
    structlog.reset_defaults()
    with capture_logs() as logs:
        log_llm_metrics(response, kind="decide", tick=7)
    assert len(logs) == 1
    entry = logs[0]
    assert entry["event"] == "llm_call"
    assert entry["kind"] == "decide"
    assert entry["tick"] == 7
    # 欄位存在且為 0 (CLI backend 行為).
    assert entry["cache_read_input_tokens"] == 0
    assert entry["cache_creation_input_tokens"] == 0
    assert entry["usage"] == {"input_tokens": 123}
