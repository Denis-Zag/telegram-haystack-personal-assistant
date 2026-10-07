"""Проверка внешних интеграций без запуска Telegram polling."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "false")

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret
from telebot import TeleBot

from app.agent_service import DogImageAnalyzer
from app.config import Settings
from app.external_tools import CatFactClient, DogImageClient, OpenMeteoClient, format_weather
from app.logging_config import configure_logging
from app.services import build_assistant


def parse_args() -> argparse.Namespace:
    """Прочитать безопасные параметры предварительной проверки."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="Путь к локальному env-файлу")
    parser.add_argument(
        "--with-vision",
        action="store_true",
        help="Дополнительно выполнить один платный анализ изображения",
    )
    parser.add_argument(
        "--with-agent-tools",
        action="store_true",
        help="Проверить, что агент сам вызывает все три инструмента",
    )
    return parser.parse_args()


def main() -> None:
    """Проверить Telegram, внешние API, ProxyAPI, Pinecone и очистить тестовые данные."""

    args = parse_args()
    env_path = Path(args.env_file).resolve()
    settings = Settings(_env_file=env_path)  # type: ignore[call-arg]
    configure_logging(settings.log_level)

    telegram_user = TeleBot(settings.telegram_bot_token).get_me()
    print(f"Telegram: OK (@{telegram_user.username})")

    weather_client = OpenMeteoClient(timeout_seconds=settings.http_timeout_seconds)
    weather = weather_client.get_current_weather("Москва")
    print(f"Open-Meteo: OK ({format_weather(weather)})")

    cat_client = CatFactClient(timeout_seconds=settings.http_timeout_seconds)
    cat_fact = cat_client.get_random_fact()
    print(f"Cat Fact API: OK ({len(cat_fact)} символов)")

    dog_client = DogImageClient(timeout_seconds=settings.http_timeout_seconds)
    dog_url = dog_client.get_random_image_url()
    print("Dog CEO API: OK")

    proxy_secret = Secret.from_token(settings.proxyapi_key)
    generator = OpenAIChatGenerator(
        api_key=proxy_secret,
        model=settings.chat_model,
        api_base_url=settings.proxyapi_base_url,
        timeout=settings.http_timeout_seconds,
        max_retries=2,
        generation_kwargs={"temperature": 0},
    )
    result = generator.run(messages=[ChatMessage.from_user("Ответь одним словом: готов")])
    print(f"ProxyAPI chat: OK ({result['replies'][0].text.strip()[:40]})")

    if args.with_vision:
        caption = DogImageAnalyzer(generator).analyze(dog_url)
        print(f"ProxyAPI vision: OK ({len(caption)} символов)")
    else:
        print("ProxyAPI vision: пропущено; добавьте --with-vision для платной проверки")

    assistant = build_assistant(settings)
    preflight_user_id = -9_060_001
    assistant.clear_memory(preflight_user_id)
    try:
        first_reply = assistant.reply(
            user_id=preflight_user_id,
            message_id=1,
            text="Проверка памяти Pinecone: код маяк-906.",
        )
        memory_reply = assistant.reply(
            user_id=preflight_user_id,
            message_id=2,
            text="Какой код я просил запомнить в предыдущем сообщении?",
        )
        count = assistant.memory_count(preflight_user_id)
        if count != 2:
            raise RuntimeError(f"Ожидались две тестовые записи, получено: {count}")
        if "906" not in memory_reply.text:
            raise RuntimeError("Агент не восстановил контрольный код из Pinecone")
        print(
            "Haystack Agent и Pinecone: OK "
            f"({len(first_reply.text)} символов, код 906 восстановлен)"
        )

        if args.with_agent_tools:
            checks = [
                (3, "Какая сейчас погода в Москве?", "get_current_weather"),
                (4, "Расскажи случайный факт о кошках.", "get_random_cat_fact"),
                (
                    5,
                    "Покажи и опиши случайное изображение собаки.",
                    "get_and_analyze_dog_image",
                ),
            ]
            for message_id, prompt, tool_name in checks:
                tool_reply = assistant.reply(
                    user_id=preflight_user_id,
                    message_id=message_id,
                    text=prompt,
                )
                if tool_reply.tool_calls.get(tool_name, 0) < 1:
                    raise RuntimeError(f"Агент не вызвал обязательный инструмент {tool_name}")
                if tool_name == "get_and_analyze_dog_image" and not tool_reply.image_url:
                    raise RuntimeError("Инструмент собаки не вернул изображение для Telegram")
                print(f"Haystack tool {tool_name}: OK")
    finally:
        assistant.clear_memory(preflight_user_id)
        print("Pinecone: тестовый namespace очищен")

    print("Preflight завершён. Telegram polling не запускался.")


if __name__ == "__main__":
    main()
