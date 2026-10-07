"""Безопасная настройка логирования приложения."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def configure_logging(level: str) -> None:
    """Настроить консольный и файловый вывод без содержимого сообщений."""

    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    logger.add(
        "logs/bot.log",
        level=level.upper(),
        rotation="5 MB",
        retention="7 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )

