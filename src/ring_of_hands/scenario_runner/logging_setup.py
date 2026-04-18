"""Structlog / logging 共用設置."""

from __future__ import annotations

import logging
from pathlib import Path

import structlog


def configure_logging(
    *,
    run_log_path: Path | None = None,
    log_level: str = "INFO",
) -> None:
    """設置 structlog 與 stdlib logging.

    Args:
        run_log_path: 若非 `None`, 另外追加寫入此檔; 檔案格式為人類可讀
            key-value.
        log_level: 環境變數 LOG_LEVEL 的值 (INFO/DEBUG/...).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if run_log_path is not None:
        run_log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(run_log_path, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        handlers=handlers,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.KeyValueRenderer(key_order=["event", "tick"], sort_keys=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


__all__ = ["configure_logging"]
