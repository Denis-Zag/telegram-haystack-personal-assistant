"""Проверки связи памяти, промпта и Haystack-агента."""

from __future__ import annotations

from typing import Any

from haystack.dataclasses import ChatMessage

from app.agent_service import PersonalAssistantService, build_context_prompt, select_tool_names


class FakeMemory:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.saved: list[tuple[int, int, str]] = []
        self.cleared: list[int] = []

    def search(self, user_id: int, query: str) -> list[str]:
        self.events.append("search")
        return ["Я живу в Казани", "Люблю гулять после 19:00"]

    def save_user_message(self, user_id: int, message_id: int, text: str) -> None:
        self.events.append("save")
        self.saved.append((user_id, message_id, text))

    def count(self, user_id: int) -> int:
        return 2

    def clear(self, user_id: int) -> None:
        self.cleared.append(user_id)


class FakeAgent:
    def __init__(self) -> None:
        self.prompt = ""
        self.tools: list[str] = []

    def run(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[str],
    ) -> dict[str, Any]:
        self.prompt = messages[0].text
        self.tools = tools
        return {
            "last_message": ChatMessage.from_assistant("Лучше гулять после 19:00."),
            "dog_image_url": "https://images.example/dog.jpg",
            "dog_image_caption": "Предположительно лабрадор.",
            "tool_call_counts": {"get_and_analyze_dog_image": 1},
        }


def test_reply_searches_before_save_and_returns_image_state() -> None:
    memory = FakeMemory()
    agent = FakeAgent()
    service = PersonalAssistantService(memory=memory, agent=agent)

    reply = service.reply(user_id=10, message_id=20, text="Когда мне гулять?")

    assert memory.events == ["search", "save"]
    assert memory.saved == [(10, 20, "Когда мне гулять?")]
    assert "Я живу в Казани" in agent.prompt
    assert "Текущий запрос пользователя:\nКогда мне гулять?" in agent.prompt
    assert reply.image_url == "https://images.example/dog.jpg"
    assert reply.image_caption == "Предположительно лабрадор."
    assert reply.tool_calls == {"get_and_analyze_dog_image": 1}
    assert agent.tools == []


def test_empty_message_does_not_call_memory_or_agent() -> None:
    memory = FakeMemory()
    agent = FakeAgent()
    service = PersonalAssistantService(memory=memory, agent=agent)

    reply = service.reply(user_id=1, message_id=1, text="   ")

    assert reply.text == "Напишите непустой вопрос."
    assert memory.events == []
    assert agent.prompt == ""


def test_context_prompt_explicitly_marks_missing_memory() -> None:
    prompt = build_context_prompt("Как меня зовут?", [])

    assert "Подходящих прошлых сообщений не найдено" in prompt
    assert prompt.endswith("Как меня зовут?")


def test_tool_selection_requires_explicit_request() -> None:
    assert select_tool_names("Я живу в Казани и люблю гулять после 19:00") == []
    assert select_tool_names("Я люблю кошек") == []
    assert select_tool_names("Расскажи о норвежской лесной кошке") == []
    assert select_tool_names("Какая сейчас погода в Казани?") == ["get_current_weather"]
    assert select_tool_names("Расскажи случайный факт о кошках") == [
        "get_random_cat_fact"
    ]
    assert select_tool_names("Покажи и опиши собаку") == [
        "get_and_analyze_dog_image"
    ]
