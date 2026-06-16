from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings


_MANAGED_FILE_SINKS: dict[Path, int] = {}


def configure_logging(settings: AppSettings, console: bool = True):
    """Configure Loguru for console and file logging."""

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / "jarvis.log"

    logger.remove()
    _MANAGED_FILE_SINKS.clear()
    if console:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            colorize=True,
            format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
        )
    add_managed_file_sink(
        log_file,
        level=settings.log_level,
    )

    logger.debug("Logging configured at {}", log_file)
    return logger


def add_managed_file_sink(
    log_file: Path,
    *,
    level: str = "DEBUG",
    filter: Callable[[dict[str, Any]], bool] | None = None,
) -> int:
    """Add one append-only Loguru file sink for a path.

    The voice loop writes frequent diagnostics while the microphone is active.
    On Windows, rotating the same active file can race with open handles, so
    live diagnostic sinks use append-only logging and are deduplicated here.
    """

    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    key = log_file.resolve()
    existing_sink = _MANAGED_FILE_SINKS.get(key)
    if existing_sink is not None:
        return existing_sink

    sink_id = logger.add(
        log_file,
        level=level,
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        enqueue=True,
        filter=filter,
    )
    _MANAGED_FILE_SINKS[key] = sink_id
    return sink_id
