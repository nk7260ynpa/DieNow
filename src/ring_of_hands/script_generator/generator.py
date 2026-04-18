"""ScriptGenerator: 依序生成 5 份閉環劇本.

每份劇本產出後立即以 `validate_closure` 比對; 失敗則 retry; 超過 `max_retries`
寫入 `issues.md` 並 raise.

本 change (`migrate-to-claude-cli-subprocess`) 將 structured output 由
Anthropic tool use 降級為「prompt 誘導 JSON」; 故:
- `_parse_response_to_script` 改從 `response.text` 讀取 JSON 字串.
- 支援 Markdown code fence (```json ... ```); 自動去除.
- `tool_use` 路徑保留為向後相容 fallback (印 DeprecationWarning).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import warnings
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ring_of_hands.llm.base import LLMCallFailedError, LLMClient, LLMResponse
from ring_of_hands.script_generator.prompt_builder import (
    build_script_request,
    build_world_environment_block,
)
from ring_of_hands.script_generator.types import (
    Persona,
    Script,
    ScriptConfig,
)
from ring_of_hands.script_generator.validator import (
    ValidationResult,
    validate_closure,
)


logger = logging.getLogger(__name__)


# Markdown code fence ```json ... ``` / ``` ... ```.
_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json|JSON)?\s*(?P<body>.*?)\s*```",
    re.DOTALL,
)


class ScriptGenerationError(Exception):
    """Script 生成失敗 (解析或 LLM 呼叫異常)."""


class ScriptValidationError(ScriptGenerationError):
    """Script 通過解析但未通過閉環驗證."""

    def __init__(self, pov_id: int, diff: tuple[dict[str, Any], ...]) -> None:
        super().__init__(
            f"script_{pov_id} 閉環驗證失敗 ({len(diff)} 筆 diff)"
        )
        self.pov_id = pov_id
        self.diff = diff


class ScriptGenerator:
    """生成 pov_1 ~ pov_5 的閉環劇本.

    Args:
        llm_client: LLMClient 實作 (ClaudeCLIClient / FakeLLMClient 等).
        personas: 長度 5 的 Persona 清單 (對應 pov_1 ~ pov_5).
        config: ScriptConfig.
        world_environment: 世界環境描述參數.
        issues_md_path: 失敗時寫入的 issues.md 路徑.
    """

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        personas: list[Persona],
        config: ScriptConfig,
        world_environment: dict[str, Any],
        issues_md_path: Path | str | None = None,
    ) -> None:
        if len(personas) != 5:
            raise ValueError("personas 必須為 5 筆 (對應 pov_1 ~ pov_5).")
        self._llm_client = llm_client
        self._personas = personas
        self._config = config
        self._world_env_block = build_world_environment_block(
            room_size=tuple(world_environment["room_size"]),
            body_start_positions=[
                tuple(p) for p in world_environment["body_start_positions"]
            ],
            button_positions=[
                tuple(p) for p in world_environment["button_positions"]
            ],
            ring_position=tuple(world_environment["ring_position"]),
            max_ticks=int(world_environment["max_ticks"]),
        )
        self._issues_md_path: Path | None = (
            Path(issues_md_path) if issues_md_path is not None else None
        )

    # --- 對外 --------------------------------------------------------------

    def generate_all(self) -> list[Script]:
        """依序生成 pov_1 ~ pov_5 的劇本."""
        scripts: list[Script] = []
        prior: Script | None = None
        for pov_id in range(1, 6):
            persona = self._personas[pov_id - 1]
            script = self._generate_one_with_retry(pov_id, persona, prior)
            scripts.append(script)
            prior = script
        return scripts

    # --- 內部 --------------------------------------------------------------

    def _generate_one_with_retry(
        self, pov_id: int, persona: Persona, prior: Script | None
    ) -> Script:
        """為單一 pov 生成劇本 (含 retry)."""
        last_error_text: str | None = None
        last_diff: tuple[dict[str, Any], ...] | None = None
        last_llm_response_ids: list[str] = []
        attempts = max(1, self._config.max_retries)

        for attempt in range(1, attempts + 1):
            logger.info(
                "script_generator: 嘗試生成 pov_%d (attempt %d/%d)",
                pov_id,
                attempt,
                attempts,
            )
            retry_feedback = self._build_retry_feedback(last_error_text, last_diff)
            request = build_script_request(
                pov_id=pov_id,
                persona=persona,
                prior_life=prior,
                world_env_block=self._world_env_block,
                config=self._config,
                retry_feedback=retry_feedback,
            )
            try:
                response = self._llm_client.call(request)
            except LLMCallFailedError as exc:
                last_error_text = f"LLM 呼叫失敗: {exc.reason}"
                logger.warning(
                    "script_generator: LLM 呼叫失敗 pov_%d attempt %d: %s",
                    pov_id,
                    attempt,
                    exc,
                )
                continue

            try:
                script = self._parse_response_to_script(response, pov_id, prior)
            except ValidationError as exc:
                last_error_text = f"Script 解析失敗: {exc}"
                logger.warning(
                    "script_generator: 解析失敗 pov_%d attempt %d: %s",
                    pov_id,
                    attempt,
                    exc,
                )
                continue
            except ScriptGenerationError as exc:
                last_error_text = str(exc)
                logger.warning(
                    "script_generator: 解析異常 pov_%d attempt %d: %s",
                    pov_id,
                    attempt,
                    exc,
                )
                continue

            validation = validate_closure(current=script, prior=prior)
            if validation.valid:
                return script
            last_diff = validation.diff
            last_error_text = f"閉環驗證失敗: {validation.message}"
            logger.warning(
                "script_generator: 閉環驗證失敗 pov_%d attempt %d, diff=%s",
                pov_id,
                attempt,
                validation.diff,
            )

        # 耗盡 retry → 寫 issues.md 並 raise.
        self._record_failure(
            pov_id=pov_id,
            last_error_text=last_error_text,
            last_diff=last_diff,
            attempts=attempts,
            llm_response_ids=last_llm_response_ids,
        )
        if last_diff is not None:
            raise ScriptValidationError(pov_id=pov_id, diff=last_diff)
        raise ScriptGenerationError(
            f"script_{pov_id} 生成達到 {attempts} 次重試仍失敗: {last_error_text}"
        )

    def _parse_response_to_script(
        self, response: LLMResponse, pov_id: int, prior: Script | None
    ) -> Script:
        """將 LLMResponse 轉為 Script.

        解析優先順序:
        1. `response.text` 為 JSON 字串 (主要路徑, 自動去除 Markdown
           code fence).
        2. `response.tool_use.input` (向後相容 fallback).
        """
        payload = _extract_script_payload(response)
        if int(payload.get("pov_id", 0)) != pov_id:
            raise ScriptGenerationError(
                f"回傳的 pov_id ({payload.get('pov_id')}) 與預期 ({pov_id}) 不符"
            )
        payload = dict(payload)
        payload["prior_life"] = (
            prior.model_dump(mode="json") if prior is not None else None
        )
        return Script.model_validate(payload)

    def _build_retry_feedback(
        self,
        last_error_text: str | None,
        last_diff: tuple[dict[str, Any], ...] | None,
    ) -> str | None:
        """組裝 retry 提示文字."""
        if not last_error_text and not last_diff:
            return None
        parts: list[str] = []
        if last_error_text:
            parts.append(last_error_text)
        if last_diff:
            parts.append("以下事件與前世記憶不一致, 請忠實重現 prior 中的內容:")
            parts.append(json.dumps(list(last_diff), ensure_ascii=False, indent=2))
        return "\n".join(parts)

    def _record_failure(
        self,
        *,
        pov_id: int,
        last_error_text: str | None,
        last_diff: tuple[dict[str, Any], ...] | None,
        attempts: int,
        llm_response_ids: list[str],
    ) -> None:
        """將失敗摘要寫入 issues.md (若有設定路徑)."""
        if self._issues_md_path is None:
            return
        timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
        lines = [
            f"\n[Specialist] [{timestamp}] [嚴重度: HIGH] "
            f"script_generator 於 pov_{pov_id} 達到 {attempts} 次重試後仍失敗.",
            f"- 最後錯誤: {last_error_text or '無'}",
        ]
        if last_diff is not None:
            lines.append(f"- 閉環 diff: {json.dumps(list(last_diff), ensure_ascii=False)}")
        if llm_response_ids:
            lines.append(f"- LLM response ids: {llm_response_ids}")
        self._issues_md_path.parent.mkdir(parents=True, exist_ok=True)
        with self._issues_md_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
            fh.write("\n")


def _strip_code_fence(text: str) -> str:
    """若 text 被 Markdown code fence 包住則去除; 否則原樣回傳."""
    stripped = text.strip()
    match = _CODE_FENCE_PATTERN.search(stripped)
    if match:
        return match.group("body").strip()
    return stripped


def _extract_script_payload(response: LLMResponse) -> dict[str, Any]:
    """從 LLMResponse 解析出 Script dict.

    主要路徑: `response.text` 為 JSON 字串 (可能包 Markdown code fence).
    Fallback: `response.tool_use.input` (向後相容).

    Raises:
        ScriptGenerationError: 無法解析 / 非 dict / 兩路徑皆無.
    """
    text = (response.text or "").strip()
    if text:
        cleaned = _strip_code_fence(text)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            if response.tool_use is not None:
                return _extract_from_tool_use(response.tool_use)
            raise ScriptGenerationError(
                f"response.text 非合法 JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ScriptGenerationError(
                f"response.text 必須為 JSON 物件, 實際型別: {type(payload).__name__}"
            )
        return payload

    if response.tool_use is not None:
        return _extract_from_tool_use(response.tool_use)
    raise ScriptGenerationError("LLM 回應為空 (text 與 tool_use 皆缺)")


def _extract_from_tool_use(tool_use: dict[str, Any]) -> dict[str, Any]:
    """向後相容: 從 tool_use.input 取 script dict."""
    warnings.warn(
        (
            "script_generator 偵測到 LLMResponse.tool_use 欄位; 此路徑為向後"
            "相容 fallback, 將於未來 change 移除. 請確保 fixture 以 "
            "response.text JSON 字串承載 script."
        ),
        DeprecationWarning,
        stacklevel=4,
    )
    name = tool_use.get("name")
    if name not in (None, "produce_script"):
        raise ScriptGenerationError(
            f"LLM 使用了非預期的 tool: {name}"
        )
    payload = tool_use.get("input")
    if not isinstance(payload, dict):
        raise ScriptGenerationError("tool_use.input 必須為 dict")
    return payload


__all__ = [
    "ScriptGenerationError",
    "ScriptGenerator",
    "ScriptValidationError",
]
