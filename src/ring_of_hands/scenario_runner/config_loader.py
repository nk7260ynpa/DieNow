"""Config 載入: 合併 YAML + `.env`, 驗證並回傳 `ScenarioConfig`.

流程:
1. 讀取 `default.yaml` (或指定 config).
2. 讀取 `configs/personas.yaml` 取得 pov_1..5 persona.
3. 以 `python-dotenv` 讀取 `.env` (若存在), 注入 `ANTHROPIC_API_KEY` 等.
4. 驗證並回傳 `ScenarioConfig`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from ring_of_hands.scenario_runner.types import ScenarioConfig, WorldConfig
from ring_of_hands.script_generator.types import Persona


class ConfigValidationError(Exception):
    """設定無效."""


class FixtureNotFoundError(Exception):
    """dry-run fixture 檔案不存在."""


def load_config(
    config_path: Path | str,
    *,
    personas_path: Path | str | None = None,
    dry_run: bool = False,
    env_overrides: dict[str, str] | None = None,
    dotenv_path: Path | str | None = None,
) -> ScenarioConfig:
    """從 YAML + env 載入 `ScenarioConfig`.

    Args:
        config_path: 主 config YAML 路徑.
        personas_path: `personas.yaml` 路徑; 預設為 `configs/personas.yaml`
            (相對於 config_path 所在目錄).
        dry_run: 是否啟用 dry-run (覆寫 config 中的對應欄位).
        env_overrides: 測試用, 覆寫 env 取值 (優先於 os.environ).
        dotenv_path: `.env` 路徑; 若為 `None` 嘗試讀取 project-root/.env.

    Raises:
        ConfigValidationError: 任一驗證失敗.
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
        # 嘗試載入 repo-root/.env (若存在).
        load_dotenv()
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)

    llm_client_raw = raw.get("llm_client", "anthropic")
    if dry_run:
        llm_client = "fake"
    else:
        llm_client = llm_client_raw

    model = env.get("PROJECT_AGENT_MODEL") or raw.get(
        "project_agent_model", "claude-sonnet-4-7"
    )
    api_key = env.get("ANTHROPIC_API_KEY") or None

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
            llm_timeout_seconds=float(raw.get("llm_timeout_seconds", 30.0)),
            llm_client=llm_client,
            project_agent_model=model,
            anthropic_api_key=api_key,
            dry_run_fixture_path=dry_run_fixture_path,
            dry_run=dry_run,
        )
    except Exception as exc:
        raise ConfigValidationError(str(exc)) from exc

    # 驗證要求.
    if config.llm_client == "anthropic" and not config.anthropic_api_key:
        raise ConfigValidationError(
            "ANTHROPIC_API_KEY is required for llm_client='anthropic'. "
            "請在 .env 中填入 ANTHROPIC_API_KEY."
        )
    if config.dry_run:
        resolved = _resolve_fixture_path(config.dry_run_fixture_path, cfg_path)
        if not resolved.exists():
            raise FixtureNotFoundError(f"dry-run fixture 不存在: {resolved}")

    return config


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
    # 嘗試 repo-root/fixture_path.
    candidate = cfg_path.resolve().parent.parent / path
    if candidate.exists():
        return candidate
    return path


__all__ = ["ConfigValidationError", "FixtureNotFoundError", "load_config"]
