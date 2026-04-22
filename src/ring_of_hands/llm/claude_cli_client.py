"""Claude Code CLI subprocess 的 LLMClient 實作.

以 `subprocess.run([cli_path, "-p", <prompt>, "--output-format", "stream-json",
"--verbose", [--model <id>]])` 呼叫 Claude Code CLI (非互動模式), 解析 stdout
NDJSON 事件流, 取最後一則 `type=result` 事件的 `result` 欄位作為
`LLMResponse.text`.

Claude Code CLI >= 2.x 規定 `-p` 搭配 `--output-format stream-json` 時必須
同時加上 `--verbose`, 否則會直接非零退出. `--verbose` 會多送一些診斷事件
(`type=system` init / 每則 `type=assistant` 細節 / 記憶體 / rate limit 等),
但最終答案仍位於 `type=result`, `_parse_ndjson` 僅依賴該事件.

認證採環境變數 `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token` 產出的
long-lived token). 該 token 可跨主機 / 容器使用, 不依賴主機 Keychain;
Linux 容器亦可承繼 Max 訂閱身份. 不再依賴 `~/.claude/` mount.

本實作不使用 `anthropic` SDK; 僅依賴 stdlib (`subprocess`, `json`, `shlex`,
`shutil`). Prompt caching 能力移除 (`CacheMetadata` 恆填 0).

設計依據: `openspec/changes/migrate-to-claude-cli-subprocess/design.md`
D-1, D-2, D-5, D-8 (D-5 認證機制經 issues.md 2026-04-18 更新: 由
`~/.claude/` mount 改為 `CLAUDE_CODE_OAUTH_TOKEN` env).
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
from typing import Any

from ring_of_hands.llm.base import (
    CacheMetadata,
    ConfigValidationError,
    LLMCallFailedError,
    LLMRequest,
    LLMResponse,
    LLMSystemBlock,
)


logger = logging.getLogger(__name__)


# prompt 超過此字元數 (約 100 KB) 時改走 stdin 以避免 argv 溢出.
PROMPT_STDIN_THRESHOLD: int = 100 * 1024


class ClaudeCLIClient:
    """以 Claude Code CLI subprocess 呼叫 LLM.

    Args:
        cli_path: `claude` 可執行檔路徑 (預設自 `CLAUDE_CLI_PATH` 讀取, 最終
            預設為 `"claude"`). 必須可於 `shutil.which` 解析.
        timeout_seconds: 預設 subprocess timeout, 若 `LLMRequest.timeout_seconds`
            有指定則以 request 為準.
        output_format: 輸出格式, 預設 `"stream-json"`; 可切換為 `"json"`
            (單次回傳, 非 NDJSON) 供未來擴充.
        skip_startup_checks: 僅供測試; 啟用後跳過建構時的 CLI 存在 / 版本
            檢查.

    Notes:
        - 先前版本曾要求 `claude_home` 目錄存在; 已於 2026-04-18 移除,
          因 macOS Keychain token 無法跨容器, 改由 `CLAUDE_CODE_OAUTH_TOKEN`
          env 注入 (由 `claude setup-token` 產生). 為保持 API 相容,
          constructor 仍接受 `claude_home=` kwarg 但不再驗證;
          實務上該參數已不影響行為.
    """

    def __init__(
        self,
        *,
        cli_path: str | None = None,
        claude_home: Any = None,  # 相容用; 2026-04-18 後已不再驗證.
        timeout_seconds: float = 180.0,
        output_format: str = "stream-json",
        skip_startup_checks: bool = False,
    ) -> None:
        del claude_home  # 保留 kwarg 僅為 API 相容, 實際不再使用.
        resolved_cli_path = cli_path if cli_path is not None else os.getenv(
            "CLAUDE_CLI_PATH", "claude"
        )

        if not skip_startup_checks:
            _validate_cli_executable(resolved_cli_path)
            _validate_cli_version(resolved_cli_path)

        self._cli_path = resolved_cli_path
        self._timeout_seconds = timeout_seconds
        self._output_format = output_format

    # --- 主介面 ------------------------------------------------------------

    def call(self, request: LLMRequest) -> LLMResponse:
        """執行一次 CLI 呼叫.

        Args:
            request: `LLMRequest`.

        Returns:
            `LLMResponse`; `text` 取自 stdout 最後一則 `type=result.result`.

        Raises:
            LLMCallFailedError: subprocess / NDJSON / CLI error 之任一狀況.
        """
        prompt = _build_prompt(request)
        timeout = request.timeout_seconds or self._timeout_seconds

        args = [self._cli_path, "-p"]
        use_stdin = len(prompt) > PROMPT_STDIN_THRESHOLD
        if use_stdin:
            # `-p` 需要 prompt 參數; 改以 stdin 傳送時以 `-` 替代, 由 CLI
            # 讀 stdin. 實務上 Claude CLI 支援 `-` 代表 stdin; 若未來行為
            # 變動, 可改為 `--stdin`.
            args.append("-")
        else:
            args.append(prompt)
        args.extend(["--output-format", self._output_format])
        # Claude CLI >= 2.x 規定 `-p` + `--output-format stream-json` 必須
        # 同時指定 `--verbose`, 否則 CLI 會直接非零退出並印出:
        #   Error: When using --print, --output-format=stream-json requires
        #   --verbose
        # (實測於 v2.1.114). `--verbose` 僅增加診斷事件量, 最終答案仍在
        # `type=result`, _parse_ndjson 能正確處理.
        if self._output_format == "stream-json":
            args.append("--verbose")
        if request.model:
            args.extend(["--model", request.model])

        logger.debug(
            "claude_cli_client: 呼叫 %s (prompt %d chars, use_stdin=%s)",
            shlex.join(args),
            len(prompt),
            use_stdin,
        )

        try:
            completed = subprocess.run(  # noqa: S603
                args,
                input=prompt if use_stdin else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMCallFailedError(reason="cli_timeout", cause=exc) from exc
        except FileNotFoundError as exc:
            raise LLMCallFailedError(reason="cli_not_found", cause=exc) from exc

        if completed.returncode != 0:
            stderr_snippet = (completed.stderr or "").strip()
            if len(stderr_snippet) > 500:
                stderr_snippet = stderr_snippet[:500] + "..."
            raise LLMCallFailedError(
                reason=f"cli_nonzero_exit:{completed.returncode}",
                cause=RuntimeError(stderr_snippet or "no stderr"),
            )

        return _parse_ndjson(completed.stdout or "")


# --- 啟動檢查 ------------------------------------------------------------


def _validate_cli_executable(cli_path: str) -> None:
    """確認 CLI 可於 PATH 中被解析."""
    resolved = shutil.which(cli_path)
    if resolved is None:
        raise ConfigValidationError(
            f"claude CLI 不可執行: {cli_path}. 請先執行 "
            "`curl -fsSL https://claude.ai/install.sh | bash` 或 "
            "`npm install -g @anthropic-ai/claude-code` 安裝, 並確認其位於 PATH."
        )


def _validate_cli_version(cli_path: str) -> None:
    """以 `claude --version` 檢查 CLI 可正常啟動."""
    try:
        result = subprocess.run(  # noqa: S603
            [cli_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ConfigValidationError(
            f"執行 `{cli_path} --version` 失敗: {exc}. 請確認 CLI 安裝無誤."
        ) from exc
    if result.returncode != 0:
        stderr_snippet = (result.stderr or "").strip()[:200]
        raise ConfigValidationError(
            f"`{cli_path} --version` 退出碼 {result.returncode}: "
            f"{stderr_snippet or '無 stderr'}. 請確認 CLI 可正常啟動."
        )


# --- Prompt 組裝 ---------------------------------------------------------


def _build_prompt(request: LLMRequest) -> str:
    """將 `LLMRequest.system_blocks + messages` 串接為單一 prompt.

    產出格式:
        ## Persona
        ...

        ## Rules
        ...

        ## Prior Life
        ...

        ## Observation / Task
        <user_message>

    若 system_blocks 的 `label` 缺失則以 "Block {i}" 作為 heading.
    """
    parts: list[str] = []
    for idx, block in enumerate(request.system_blocks):
        heading = _label_to_heading(block.label, idx)
        parts.append(f"## {heading}\n{block.text}")

    user_message = _extract_user_message(request)
    parts.append(f"## Observation / Task\n{user_message}")

    return "\n\n".join(parts)


def _label_to_heading(label: str | None, idx: int) -> str:
    """將 block label 轉為 Markdown 標題."""
    mapping: dict[str, str] = {
        "persona": "Persona",
        "rules": "Rules",
        "prior_life": "Prior Life",
        "world_env": "World Environment",
    }
    if label and label in mapping:
        return mapping[label]
    if label:
        return label.replace("_", " ").title()
    return f"Block {idx + 1}"


def _extract_user_message(request: LLMRequest) -> str:
    """取 messages 的最後一則 user message."""
    for msg in reversed(request.messages):
        if msg.role == "user":
            return msg.content
    if request.messages:
        return request.messages[-1].content
    return ""


# --- NDJSON 解析 ---------------------------------------------------------


def _parse_ndjson(stdout: str) -> LLMResponse:
    """解析 Claude CLI `--output-format stream-json` 的 stdout NDJSON.

    流程:
        1. 按 `\\n` 切行; 對每行做 `json.loads`; 無法解析的行記 warning
           並忽略.
        2. 若出現 `type=error` 事件 → raise `LLMCallFailedError(
           reason="cli_error:<err>")`.
        3. 收集所有 `type=result` 事件, 取最末一則.
        4. 若 0 則 → raise `LLMCallFailedError(reason="no_result_event")`.
        5. 若 `result` 事件缺 `result` 欄位 → raise `LLMCallFailedError(
           reason="result_missing_text")`.
        6. 從 `result.usage` (若存在) 填入 `input_tokens` / `output_tokens`;
           `cache_read_input_tokens` / `cache_creation_input_tokens` 恆為 0.

    Args:
        stdout: CLI stdout 文字.

    Returns:
        `LLMResponse`.

    Raises:
        LLMCallFailedError: 依據上方流程.
    """
    if not stdout.strip():
        raise LLMCallFailedError(reason="ndjson_parse_error")

    events: list[dict[str, Any]] = []
    total_lines = 0
    failed_lines = 0
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        total_lines += 1
        try:
            ev = json.loads(line)
        except json.JSONDecodeError as exc:
            failed_lines += 1
            logger.warning(
                "claude_cli_client: 無法解析 NDJSON 行 (忽略): %s (err=%s)",
                line[:200],
                exc,
            )
            continue
        if isinstance(ev, dict):
            events.append(ev)
        else:
            failed_lines += 1
            logger.warning(
                "claude_cli_client: NDJSON 行非 object 型別 (忽略): %s",
                line[:200],
            )

    if total_lines > 0 and failed_lines == total_lines:
        raise LLMCallFailedError(reason="ndjson_parse_error")

    result_event: dict[str, Any] | None = None
    for ev in events:
        if ev.get("type") == "error":
            err_text = _extract_error_text(ev)
            raise LLMCallFailedError(reason=f"cli_error:{err_text}")
        if ev.get("type") == "result":
            result_event = ev

    if result_event is None:
        raise LLMCallFailedError(reason="no_result_event")

    final_text = result_event.get("result")
    if not isinstance(final_text, str):
        raise LLMCallFailedError(reason="result_missing_text")

    usage_dict: dict[str, int] = {}
    usage_raw = result_event.get("usage")
    if isinstance(usage_raw, dict):
        for key in ("input_tokens", "output_tokens"):
            val = usage_raw.get(key)
            if isinstance(val, int):
                usage_dict[key] = val

    return LLMResponse(
        text=final_text,
        tool_use=None,
        usage=usage_dict,
        cache=CacheMetadata(
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        raw={"stdout_events_count": len(events)},
    )


def _extract_error_text(event: dict[str, Any]) -> str:
    """從 type=error 事件取得可讀錯誤訊息."""
    err = event.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("error") or str(err)
        return str(msg)
    if isinstance(err, str):
        return err
    if event.get("message"):
        return str(event["message"])
    return "unknown_cli_error"


__all__ = [
    "ClaudeCLIClient",
    "PROMPT_STDIN_THRESHOLD",
]
