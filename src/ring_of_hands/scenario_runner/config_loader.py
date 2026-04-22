"""Config 載入: 合併 YAML + `.env`, 驗證並回傳 `ScenarioConfig`.

流程:
1. 讀取 `default.yaml` (或指定 config).
2. 讀取 `configs/personas.yaml` 取得 pov_1..5 persona.
3. 以 `python-dotenv` 讀取 `.env` (若存在), 注入 `CLAUDE_CLI_PATH` 等.
4. 驗證並回傳 `ScenarioConfig`.
5. 若 `dry_run=False` 且 `llm_client="claude_cli"`, 執行下列預啟動檢查:
   - `shutil.which(cli_path)` 不為 None.
   - `subprocess.run([cli_path, "--version"], timeout=5, check=False)` exit 0.
   - `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY` 至少其一被設定
     (2026-04-18 修正: macOS Keychain token 無法跨容器, `~/.claude/`
     目錄 mount 無法承繼認證; 正確作法是透過 `claude setup-token` 產生
     long-lived token 並以 env 注入).
   任一失敗 raise `ConfigValidationError`.

本 change (`migrate-to-claude-cli-subprocess`) 將 `ConfigValidationError`
統一由 `ring_of_hands.llm.base` 匯出; `scenario_runner.config_loader` 仍
re-export 以保持向後相容 import 路徑.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from ring_of_hands.llm.base import (
    ConfigValidationError as ConfigValidationError,
)
from ring_of_hands.scenario_runner.types import ScenarioConfig, WorldConfig
from ring_of_hands.script_generator.types import Persona


# 認證環境變數名稱; 優先使用 `CLAUDE_CODE_OAUTH_TOKEN` (由 `claude setup-token`
# 產生, 支援 Max 訂閱計費), fallback 到 `ANTHROPIC_API_KEY` (API key 計費).
_OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
_API_KEY_ENV = "ANTHROPIC_API_KEY"


class FixtureNotFoundError(Exception):
    """dry-run fixture 檔案不存在."""


def load_config(
    config_path: Path | str,
    *,
    personas_path: Path | str | None = None,
    dry_run: bool = False,
    env_overrides: dict[str, str] | None = None,
    dotenv_path: Path | str | None = None,
    skip_cli_checks: bool = False,
) -> ScenarioConfig:
    """從 YAML + env 載入 `ScenarioConfig`.

    Args:
        config_path: 主 config YAML 路徑.
        personas_path: `personas.yaml` 路徑; 預設為 `configs/personas.yaml`
            (相對於 config_path 所在目錄).
        dry_run: 是否啟用 dry-run; 啟用時 MUST 跳過 Claude CLI 相關檢查
            (dry-run 必須離線可跑).
        env_overrides: 測試用, 覆寫 env 取值 (優先於 os.environ).
        dotenv_path: `.env` 路徑; 若為 `None` 嘗試讀取 project-root/.env.
        skip_cli_checks: 僅供測試; 即使非 dry-run 亦跳過 CLI 預啟動檢查.

    Raises:
        ConfigValidationError: 任一驗證失敗, 包含 CLI 不可執行或 claude_home
            目錄不存在.
        FixtureNotFoundError: 啟用 dry-run 但 fixture 檔案不存在.
    """
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        raise ConfigValidationError(f"{cfg_path} not found")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    # Personas.
    if personas_path is None:
        personas_path = cfg_path.parent / "personas.yaml"
    personas_file = Path(personas_path)
    if not personas_file.exists():
        raise ConfigValidationError(f"{personas_file} not found")
    personas_raw = yaml.safe_load(personas_file.read_text(encoding="utf-8")) or {}
    pov_personas = _parse_personas(personas_raw)

    # env / .env.
    if dotenv_path is not None:
        load_dotenv(dotenv_path=Path(dotenv_path))
    else:
        load_dotenv()
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)

    llm_client_raw = raw.get("llm_client", "claude_cli")
    # 相容: 舊 YAML 可能仍寫 "anthropic"; 自動改為 "claude_cli" 並於日誌
    # 提示 (本 change 已移除 Anthropic SDK 後端).
    if llm_client_raw == "anthropic":
        llm_client_raw = "claude_cli"
    if dry_run:
        llm_client = "fake"
    else:
        llm_client = llm_client_raw

    model = env.get("PROJECT_AGENT_MODEL") or raw.get(
        "project_agent_model", "claude-sonnet-4-6"
    )
    cli_path = env.get("CLAUDE_CLI_PATH") or raw.get("cli_path", "claude")
    claude_home = (
        (env.get("CLAUDE_HOME") or "").strip()
        or raw.get("claude_home")
        or "~/.claude"
    )
    try:
        llm_timeout_seconds = float(
            env.get("CLAUDE_CLI_TIMEOUT_SECONDS")
            or raw.get("llm_timeout_seconds", 180.0)
        )
    except ValueError as exc:
        raise ConfigValidationError(
            f"CLAUDE_CLI_TIMEOUT_SECONDS 不為合法數字: {exc}"
        ) from exc

    world = WorldConfig(
        room_size=tuple(raw.get("room_size", (10, 10))),
        body_start_positions=_to_coords(raw.get("body_start_positions", [])),
        button_positions=_to_coords(raw.get("button_positions", [])),
        ring_position=tuple(raw.get("ring_position", (5, 5))),
    )

    dry_run_fixture_path = Path(raw.get("dry_run_fixture_path", "tests/fixtures/dry_run.yaml"))

    pov6_persona_raw = raw.get("pov6_persona") or {}
    pov6_persona = Persona(
        name=str(pov6_persona_raw.get("name", "被困的玩家")),
        description=str(pov6_persona_raw.get("description", "")),
        traits=tuple(pov6_persona_raw.get("traits", [])),
    )

    try:
        config = ScenarioConfig(
            world=world,
            pov1_to_5_personas=tuple(pov_personas),
            pov6_persona=pov6_persona,
            max_ticks=int(raw.get("max_ticks", 50)),
            max_retries=int(raw.get("max_retries", 3)),
            max_speak_length=int(raw.get("max_speak_length", 512)),
            enable_realtime_chat=bool(raw.get("enable_realtime_chat", True)),
            llm_timeout_seconds=llm_timeout_seconds,
            llm_client=llm_client,
            project_agent_model=model,
            cli_path=cli_path,
            claude_home=claude_home,
            dry_run_fixture_path=dry_run_fixture_path,
            dry_run=dry_run,
        )
    except Exception as exc:
        raise ConfigValidationError(str(exc)) from exc

    # dry-run fixture 檢查.
    if config.dry_run:
        resolved = _resolve_fixture_path(config.dry_run_fixture_path, cfg_path)
        if not resolved.exists():
            raise FixtureNotFoundError(f"dry-run fixture 不存在: {resolved}")
    else:
        # 非 dry-run 才做 CLI 預啟動檢查.
        if config.llm_client == "claude_cli" and not skip_cli_checks:
            _validate_claude_cli_environment(
                cli_path=config.cli_path,
                env=env,
            )

    return config


def _validate_claude_cli_environment(
    *, cli_path: str, env: dict[str, str]
) -> None:
    """執行 Claude CLI 預啟動檢查.

    2026-04-18 修正: `~/.claude/` 目錄存在 (`claude login`) 在 macOS 上
    並不能實際承繼到容器, 因 OAuth token 存於 macOS Keychain; 改為檢查
    `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY` 是否設定.

    Args:
        cli_path: `claude` 可執行檔路徑.
        env: 已合併 os.environ 與 `.env` 的 env dict.

    Raises:
        ConfigValidationError: 任一檢查失敗.
    """
    # 1. shutil.which.
    if shutil.which(cli_path) is None:
        raise ConfigValidationError(
            f"claude CLI 不可執行: {cli_path}. 請先安裝 Claude Code CLI "
            "(例如 `curl -fsSL https://claude.ai/install.sh | bash`) "
            "並確認其位於 PATH."
        )
    # 2. claude --version exit 0.
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
    # 3. 認證 env: CLAUDE_CODE_OAUTH_TOKEN 或 ANTHROPIC_API_KEY 至少其一.
    oauth = (env.get(_OAUTH_TOKEN_ENV) or "").strip()
    api_key = (env.get(_API_KEY_ENV) or "").strip()
    if not oauth and not api_key:
        raise ConfigValidationError(
            f"缺少 Claude 認證 env: 需設定 {_OAUTH_TOKEN_ENV} (推薦, 走 "
            "Max 訂閱計費) 或 ANTHROPIC_API_KEY (走 API key 計費). "
            "建議先於主機執行 `claude setup-token` 產生 long-lived "
            f"OAuth token, 再以 `{_OAUTH_TOKEN_ENV}=<token>` 寫入 `.env`."
        )


def _parse_personas(raw: dict[str, Any]) -> list[Persona]:
    """解析 personas.yaml 為 Persona 清單."""
    items = raw.get("personas") or []
    if len(items) != 5:
        raise ConfigValidationError("personas.yaml 必須包含 5 筆 (pov_1..5)")
    personas: list[Persona] = []
    for item in items:
        personas.append(
            Persona(
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                traits=tuple(item.get("traits", [])),
            )
        )
    return personas


def _to_coords(raw: list[Any]) -> tuple[tuple[int, int], ...]:
    return tuple((int(p[0]), int(p[1])) for p in raw)


def _resolve_fixture_path(path: Path, cfg_path: Path) -> Path:
    """將 fixture 路徑解析為絕對路徑.

    若 path 已為絕對或存在於當前工作目錄, 直接回傳; 否則嘗試以 cfg_path
    的上上層 (repo root) 為基準.
    """
    if path.is_absolute() and path.exists():
        return path
    if path.exists():
        return path
    candidate = cfg_path.resolve().parent.parent / path
    if candidate.exists():
        return candidate
    return path


__all__ = [
    "ConfigValidationError",
    "FixtureNotFoundError",
    "load_config",
]
