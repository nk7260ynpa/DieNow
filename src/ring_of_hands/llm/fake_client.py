"""Fake LLM Client 供測試與 dry-run 使用.

支援三種用途:
- script-generator: 以 `add_script_response` 預錄 `LLMResponse`, 其 tool_use
  為 `{"name": "produce_script", "input": <Script 序列化 dict>}`.
- project-agent (pov_6 decide): 以 `add_decide_response` 預錄 action 回應.
- project-agent (realtime_reply): 以 `add_realtime_reply_response` 預錄
  對話回應.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from ring_of_hands.llm.base import (
    CacheMetadata,
    LLMCallFailedError,
    LLMRequest,
    LLMResponse,
)


class FakeClientFixture:
    """從 YAML fixture 載入的 FakeAnthropicClient 設定."""

    def __init__(
        self,
        *,
        scripts: list[dict[str, Any]] | None = None,
        project_agent_actions: list[dict[str, Any]] | None = None,
        realtime_replies: dict[str, list[str]] | None = None,
    ) -> None:
        self.scripts = scripts or []
        self.project_agent_actions = project_agent_actions or []
        self.realtime_replies = realtime_replies or {}

    @classmethod
    def from_yaml(cls, path: Path | str) -> "FakeClientFixture":
        """從 YAML 讀取 fixture."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Fixture 檔案不存在: {p}")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(
            scripts=data.get("scripts", []),
            project_agent_actions=data.get("project_agent_actions", []),
            realtime_replies=data.get("realtime_replies", {}),
        )


class FakeAnthropicClient:
    """離線用 FakeAnthropicClient.

    以 request.metadata 中的 `purpose` 欄位決定該回傳哪種 response:
    - `purpose="script_generation"`: 依照 `metadata.pov_id` 回傳對應 script.
    - `purpose="agent_decide"`: 依序 pop `project_agent_actions`.
    - `purpose="realtime_reply"`: 依照 `metadata.pov_id` 的對話清單依序 pop.

    若測試要模擬失敗, 可呼叫 `queue_error` 預錄錯誤.
    """

    def __init__(self, fixture: FakeClientFixture | None = None) -> None:
        self._fixture = fixture or FakeClientFixture()
        # 動態追加的 queues.
        self._script_responses: dict[int, list[LLMResponse]] = defaultdict(list)
        self._decide_responses: list[LLMResponse] = []
        self._realtime_responses: dict[int, list[str]] = defaultdict(list)
        self._error_queue: list[LLMCallFailedError] = []
        self._call_log: list[tuple[str, LLMRequest]] = []
        self._load_from_fixture()

    # --- Fixture 載入 ------------------------------------------------------

    def _load_from_fixture(self) -> None:
        """將 fixture 轉成 queues."""
        for script in self._fixture.scripts:
            pov_id = int(script["pov_id"])
            response = LLMResponse(
                text="",
                tool_use={"name": "produce_script", "input": script},
                usage={
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cache_read_input_tokens": 800,
                },
                cache=CacheMetadata(cache_read_input_tokens=800),
                raw={},
            )
            self._script_responses[pov_id].append(response)

        for action in self._fixture.project_agent_actions:
            response = LLMResponse(
                text="",
                tool_use={"name": "submit_action", "input": action},
                usage={"input_tokens": 1200, "output_tokens": 50},
                cache=CacheMetadata(
                    cache_read_input_tokens=1000,
                    cache_creation_input_tokens=0,
                ),
                raw={},
            )
            self._decide_responses.append(response)

        for pov_id_str, replies in self._fixture.realtime_replies.items():
            pov_id_int = int(pov_id_str)
            for text in replies:
                self._realtime_responses[pov_id_int].append(text)

    # --- 動態追加 ----------------------------------------------------------

    def add_script_response(self, pov_id: int, response: LLMResponse) -> None:
        """手動追加 script 生成的 response (測試用)."""
        self._script_responses[pov_id].append(response)

    def add_decide_response(self, response: LLMResponse) -> None:
        """手動追加 pov_6 decide 的 response."""
        self._decide_responses.append(response)

    def add_realtime_reply_response(self, pov_id: int, text: str) -> None:
        """手動追加 realtime reply."""
        self._realtime_responses[pov_id].append(text)

    def queue_error(self, error: LLMCallFailedError) -> None:
        """下一次 call 會 raise 此錯誤."""
        self._error_queue.append(error)

    # --- 主介面 ------------------------------------------------------------

    @property
    def call_log(self) -> list[tuple[str, LLMRequest]]:
        """回傳所有呼叫紀錄 (purpose, request)."""
        return list(self._call_log)

    def call(self, request: LLMRequest) -> LLMResponse:
        """執行 fake 呼叫."""
        purpose = str(request.metadata.get("purpose", ""))
        self._call_log.append((purpose, request))
        if self._error_queue:
            raise self._error_queue.pop(0)
        if purpose == "script_generation":
            pov_id = int(request.metadata.get("pov_id", 0))
            queue = self._script_responses.get(pov_id)
            if not queue:
                raise LLMCallFailedError(
                    reason=f"fake_no_script_response_for_pov_{pov_id}"
                )
            return queue.pop(0)
        if purpose == "agent_decide":
            if not self._decide_responses:
                # 若耗盡則自動回覆 wait (安全降級).
                return LLMResponse(
                    text="",
                    tool_use={"name": "submit_action", "input": {"action": "wait"}},
                    usage={"input_tokens": 100, "output_tokens": 5},
                    cache=CacheMetadata(),
                    raw={},
                )
            return self._decide_responses.pop(0)
        if purpose == "realtime_reply":
            pov_id = int(request.metadata.get("pov_id", 0))
            queue = self._realtime_responses.get(pov_id)
            if queue:
                text = queue.pop(0)
            else:
                text = "..."
            return LLMResponse(
                text=text,
                tool_use=None,
                usage={"input_tokens": 200, "output_tokens": 20},
                cache=CacheMetadata(cache_read_input_tokens=150),
                raw={},
            )
        raise LLMCallFailedError(reason=f"fake_unknown_purpose_{purpose}")


__all__ = ["FakeAnthropicClient", "FakeClientFixture"]
