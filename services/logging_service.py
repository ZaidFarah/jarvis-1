from __future__ import annotations

import sys

from loguru import logger

from config.settings import AppSettings


def configure_logging(settings: AppSettings):
    """Configure Loguru for console and file logging."""

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / "jarvis.log"

    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
    logger.add(
        log_file,
        level=settings.log_level,
        rotation="1 MB",
        retention="7 days",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
    )

    logger.debug("Logging configured at {}", log_file)
    return logger
