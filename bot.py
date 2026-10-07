"""Точка запуска Telegram polling."""

from __future__ import annotations

from loguru import logger

from app.config import get_settings
from app.logging_config import configure_logging
from app.services import build_assistant
from app.telegram_bot import create_bot


def main() -> None:
    """Собрать приложение и запустить единственный polling-процесс."""

    settings = get_settings()
    configure_logging(settings.log_level)
    assistant = build_assistant(settings)
    bot = create_bot(settings.telegram_bot_token, assistant)
    bot.remove_webhook()
    logger.info("Telegram-бот запускает polling")
    try:
        bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
    finally:
        logger.info("Telegram-бот остановлен")


if __name__ == "__main__":
    main()
