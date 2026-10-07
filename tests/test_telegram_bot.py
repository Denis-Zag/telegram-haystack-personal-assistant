"""Интеграционная проверка обработчика Telegram-сообщения."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.models import AssistantReply
from app.telegram_bot import create_bot


class FakeAssistant:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    def reply(self, **kwargs: Any) -> AssistantReply:
        self.request = kwargs
        return AssistantReply(
            text="Изображение готово.",
            image_url="https://images.example/dog.jpg",
            image_caption="Предположительно лабрадор.",
        )

    def memory_count(self, user_id: int) -> int:
        return 0

    def clear_memory(self, user_id: int) -> None:
        return None


def test_text_handler_passes_identity_and_sends_photo(monkeypatch: Any) -> None:
    assistant = FakeAssistant()
    bot = create_bot("1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE", assistant)
    sent_photos: list[tuple[int, str, str]] = []
    sent_messages: list[tuple[int, str]] = []
    monkeypatch.setattr(
        bot,
        "send_photo",
        lambda chat_id, url, caption: sent_photos.append((chat_id, url, caption)),
    )
    monkeypatch.setattr(
        bot,
        "send_message",
        lambda chat_id, text: sent_messages.append((chat_id, text)),
    )
    text_handler = next(
        handler["function"]
        for handler in bot.message_handlers
        if handler["function"].__name__ == "text_handler"
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=55),
        from_user=SimpleNamespace(id=77),
        message_id=99,
        text="Покажи собаку",
    )

    text_handler(message)

    assert assistant.request == {
        "user_id": 77,
        "message_id": 99,
        "text": "Покажи собаку",
    }
    assert sent_photos == [
        (55, "https://images.example/dog.jpg", "Предположительно лабрадор.")
    ]
    assert sent_messages == []
