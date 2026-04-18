"""CLI 實作: `python -m ring_of_hands.cli run --config <path>`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ring_of_hands.scenario_runner.config_loader import (
    ConfigValidationError,
    FixtureNotFoundError,
    load_config,
)
from ring_of_hands.scenario_runner.logging_setup import configure_logging
from ring_of_hands.scenario_runner.runner import ScenarioRunner


logger = logging.getLogger("ring_of_hands.cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ring-of-hands")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="執行攜手之戒關卡")
    run_parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="主 YAML config 路徑",
    )
    run_parser.add_argument(
        "--personas",
        type=Path,
        default=None,
        help="personas.yaml 路徑 (預設為 config 同目錄下的 personas.yaml)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="使用 FakeAnthropicClient 與 dry_run fixture, 不呼叫真實 LLM",
    )
    run_parser.add_argument(
        "--log-level",
        default="INFO",
        help="日誌等級 (DEBUG/INFO/WARNING/ERROR)",
    )
    run_parser.add_argument(
        "--log-dir",
        default=Path("logs"),
        type=Path,
        help="logs 目錄",
    )
    return parser


def cli_main(argv: list[str]) -> int:
    """CLI 入口函式.

    Args:
        argv: 命令列參數清單 (不含 program name).

    Returns:
        exit code: 0 正常; 非 0 表示錯誤類型.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    parser.error(f"未知指令: {args.command}")
    return 2


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        config = load_config(
            args.config,
            personas_path=args.personas,
            dry_run=bool(args.dry_run),
        )
    except ConfigValidationError as exc:
        print(f"ConfigValidationError: {exc}", file=sys.stderr)
        return 2
    except FixtureNotFoundError as exc:
        print(f"FixtureNotFoundError: {exc}", file=sys.stderr)
        return 3

    configure_logging(log_level=args.log_level)
    runner = ScenarioRunner(config, log_dir=args.log_dir)
    summary = runner.run()

    print(
        json.dumps(
            {
                "outcome": summary.outcome.model_dump(),
                "total_ticks": summary.total_ticks,
                "alive_bodies_at_end": summary.alive_bodies_at_end,
                "lit_buttons_at_end": summary.lit_buttons_at_end,
                "event_log_path": summary.event_log_path,
                "summary_path": summary.event_log_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary.outcome.result == "WIN" else 1


__all__ = ["cli_main"]
