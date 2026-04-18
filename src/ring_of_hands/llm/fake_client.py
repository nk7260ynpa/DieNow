"""Fake LLM Client 供測試與 dry-run 使用.

本 class 名為 `FakeLLMClient` (原名 `FakeAnthropicClient`, 於本 change
由 Anthropic SDK 遷移至 Claude Code CLI subprocess 時更名). `FakeLLMClient`
是實作 `LLMClient` Protocol 的通用 fake, **不綁定特定 backend**.

支援三種用途:
- script-generator: 以 fixture 的 `scripts` 或 `add_script_response` 預錄
  `LLMResponse`; `text` 為 script dict 的 JSON 字串.
- project-agent (pov_6 decide): 以 fixture 的 `project_agent_actions` 或
  `add_decide_response` 預錄 action; `text` 為 action dict 的 JSON 字串.
- project-agent (realtime_reply): 以 fixture 的 `realtime_replies` 或
  `add_realtime_reply_response` 預錄文字回覆.

向後相容: fixture 或動態追加的 `LLMResponse.tool_use` 仍被接受 (舊測試
檔案可能依賴此路徑); 但會於載入時印出 `DeprecationWarning` 提示升級.
"""

from __future__ import annotations

import json
import warnings
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
    """從 YAML fixture 載入的 FakeLLMClient 設定.

    Attributes:
        scripts: pov_1 ~ pov_5 的預錄劇本 dict 清單.
        project_agent_actions: pov_6 每個 tick 的 action dict (循序取用).
        realtime_replies: {pov_id_str: [text, ...]}.
    """

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


class FakeLLMClient:
    """離線用 FakeLLMClient.

    以 `request.metadata.purpose` 決定回傳哪種 response:
    - `purpose="script_generation"`: 依照 `metadata.pov_id` 回傳對應 script.
    - `purpose="agent_decide"`: 依序 pop `project_agent_actions`.
    - `purpose="realtime_reply"`: 依照 `metadata.pov_id` 的對話清單依序 pop.

    若測試要模擬失敗, 可呼叫 `queue_error` 預錄 `LLMCallFailedError`.
    """

    def __init__(self, fixture: FakeClientFixture | None = None) -> None:
        self._fixture = fixture or FakeClientFixture()
        self._script_responses: dict[int, list[LLMResponse]] = defaultdict(list)
        self._decide_responses: list[LLMResponse] = []
        self._realtime_responses: dict[int, list[str]] = defaultdict(list)
        self._error_queue: list[LLMCallFailedError] = []
        self._call_log: list[tuple[str, LLMRequest]] = []
        self._load_from_fixture()

    # --- Fixture 載入 ------------------------------------------------------

    def _load_from_fixture(self) -> None:
        """將 fixture 轉成 queues; 以 JSON text 為主要載體."""
        for script in self._fixture.scripts:
            pov_id = int(script["pov_id"])
            self._script_responses[pov_id].append(
                _build_script_response(script)
            )

        for action in self._fixture.project_agent_actions:
            self._decide_responses.append(_build_action_response(action))

        for pov_id_str, replies in self._fixture.realtime_replies.items():
            pov_id_int = int(pov_id_str)
            for text in replies:
                self._realtime_responses[pov_id_int].append(text)

    # --- 動態追加 ----------------------------------------------------------

    def add_script_response(self, pov_id: int, response: LLMResponse) -> None:
        """手動追加 script 生成的 response (測試用)."""
        _maybe_warn_legacy_tool_use(response, context=f"script_pov_{pov_id}")
        self._script_responses[pov_id].append(response)

    def add_decide_response(self, response: LLMResponse) -> None:
        """手動追加 pov_6 decide 的 response."""
        _maybe_warn_legacy_tool_use(response, context="decide")
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
                # 耗盡時自動回覆 wait (安全降級).
                return _build_action_response({"action": "wait"})
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
                cache=CacheMetadata(),
                raw={},
            )
        raise LLMCallFailedError(reason=f"fake_unknown_purpose_{purpose}")


# --- Response builders ----------------------------------------------------


def _build_script_response(script: dict[str, Any]) -> LLMResponse:
    """將 script dict 序列化為 `LLMResponse.text` (JSON 字串).

    不再產生 `tool_use` 欄位; 符合 `ClaudeCLIClient` 的自然回傳格式.
    """
    return LLMResponse(
        text=json.dumps(script, ensure_ascii=False),
        tool_use=None,
        usage={"input_tokens": 1000, "output_tokens": 200},
        cache=CacheMetadata(),
        raw={},
    )


def _build_action_response(action: dict[str, Any]) -> LLMResponse:
    """將 action dict 序列化為 `LLMResponse.text` (JSON 字串)."""
    return LLMResponse(
        text=json.dumps(action, ensure_ascii=False),
        tool_use=None,
        usage={"input_tokens": 1200, "output_tokens": 50},
        cache=CacheMetadata(),
        raw={},
    )


def _maybe_warn_legacy_tool_use(response: LLMResponse, *, context: str) -> None:
    """若 response 仍帶 `tool_use` 欄位, 印出 DeprecationWarning."""
    if response.tool_use is not None:
        warnings.warn(
            (
                f"FakeLLMClient 收到帶 tool_use 的舊 fixture ({context}); "
                "建議改用 response.text JSON 字串以符合 ClaudeCLIClient 的自然回傳格式. "
                "此向後相容路徑將於未來 change 移除."
            ),
            DeprecationWarning,
            stacklevel=3,
        )


# --- 向後相容 alias -------------------------------------------------------


# 提供 `FakeAnthropicClient` 作為舊名稱的別名, 以保相容; 新程式碼請改用
# `FakeLLMClient`.
FakeAnthropicClient = FakeLLMClient


__all__ = [
    "FakeAnthropicClient",
    "FakeClientFixture",
    "FakeLLMClient",
]
