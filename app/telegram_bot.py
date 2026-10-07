"""Обработчики Telegram для персонального ассистента."""

from __future__ import annotations

from loguru import logger
from telebot import TeleBot, types

from app.agent_service import PersonalAssistantService

START_TEXT = """
Привет! Я персональный ассистент на Haystack.

Я умею:
- помнить ваши сообщения в Pinecone;
- отвечать с учётом прошлого контекста;
- получать текущую погоду;
- находить факты о кошках;
- получать и анализировать изображения собак.

Команды: /help, /memory_status, /clear.
""".strip()

HELP_TEXT = """
Примеры запросов:
- Какая сейчас погода в Москве?
- Расскажи случайный факт о кошках.
- Покажи и опиши случайную собаку.
- Запомни, что я живу в Казани и люблю гулять после 19:00.

/memory_status — число сохранённых сообщений.
/clear — удалить только вашу память.
""".strip()


def create_bot(token: str, assistant: PersonalAssistantService) -> TeleBot:
    """Создать Telegram-бота и зарегистрировать обработчики."""

    bot = TeleBot(token, parse_mode=None)

    @bot.message_handler(commands=["start"])
    def start_handler(message: types.Message) -> None:
        bot.send_message(message.chat.id, START_TEXT)

    @bot.message_handler(commands=["help"])
    def help_handler(message: types.Message) -> None:
        bot.send_message(message.chat.id, HELP_TEXT)

    @bot.message_handler(commands=["memory_status"])
    def memory_status_handler(message: types.Message) -> None:
        try:
            count = assistant.memory_count(message.from_user.id)
            bot.send_message(message.chat.id, f"В вашей памяти сообщений: {count}.")
        except Exception:
            logger.exception("Ошибка команды /memory_status")
            bot.send_message(message.chat.id, "Не удалось проверить память. Попробуйте позже.")

    @bot.message_handler(commands=["clear"])
    def clear_handler(message: types.Message) -> None:
        try:
            assistant.clear_memory(message.from_user.id)
            bot.send_message(message.chat.id, "Ваша память очищена.")
        except Exception:
            logger.exception("Ошибка команды /clear")
            bot.send_message(message.chat.id, "Не удалось очистить память. Попробуйте позже.")

    @bot.message_handler(
        content_types=["text"],
        func=lambda message: not message.text.startswith("/"),
    )
    def text_handler(message: types.Message) -> None:
        try:
            reply = assistant.reply(
                user_id=message.from_user.id,
                message_id=message.message_id,
                text=message.text,
            )
            if reply.image_url:
                caption = reply.image_caption or reply.text
                bot.send_photo(message.chat.id, reply.image_url, caption=caption[:1024])
            else:
                bot.send_message(message.chat.id, reply.text)
        except Exception:
            logger.exception("Непредвиденная ошибка обработки Telegram-сообщения")
            bot.send_message(
                message.chat.id,
                "Не удалось обработать запрос. Попробуйте ещё раз немного позже.",
            )

    @bot.message_handler(func=lambda _message: True)
    def fallback_handler(message: types.Message) -> None:
        bot.send_message(
            message.chat.id,
            "Пока я обрабатываю только текстовые сообщения.",
        )

    return bot
