"""Haystack-агент и прикладная логика ответа пользователю."""

from __future__ import annotations

import re
from typing import Annotated, Any, Protocol

from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage, ImageContent
from haystack.tools import Tool, tool
from loguru import logger

from app.external_tools import (
    CatFactClient,
    DogImageClient,
    ExternalApiError,
    OpenMeteoClient,
    format_weather,
)
from app.memory import ConversationMemory
from app.models import AssistantReply

SYSTEM_PROMPT = """
Ты персональный помощник в Telegram. Отвечай по-русски, кратко и по делу.

У тебя есть три внешних инструмента:
- get_current_weather: всегда используй его для текущей погоды в городе;
- get_random_cat_fact: используй, когда пользователь просит факт о кошках;
- get_and_analyze_dog_image: используй, когда пользователь просит изображение
  собаки, определить предполагаемую породу или рассказать о ней по фотографии.

Инструменты вызываются только по явной просьбе или вопросу. Обычное сообщение о
себе, например «Я живу в Казани» или «Я люблю кошек», нужно спокойно подтвердить
и запомнить без вызова погоды, случайного факта или изображения. Не угадывай
желание пользователя только по упоминанию города, кошки или собаки.

Не придумывай актуальную погоду, факты или результат анализа изображения.
Если инструмент сообщил об ошибке, честно объясни, что данные получить не удалось.

В сообщении может быть раздел «Контекст из Pinecone». Это прошлые фразы самого
пользователя, найденные по смыслу. Используй их только когда они относятся к
текущему вопросу. Не называй их ответами ассистента и не выдумывай отсутствующие
сведения. Если подходящего контекста нет, не утверждай, что помнишь факт.
""".strip()


class AgentRunner(Protocol):
    """Минимальный контракт Haystack Agent для удобного тестирования."""

    def run(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[str],
    ) -> dict[str, Any]: ...


class DogImageAnalyzer:
    """Проанализировать изображение собаки с помощью мультимодальной модели."""

    def __init__(self, generator: OpenAIChatGenerator) -> None:
        self._generator = generator

    def analyze(self, image_url: str) -> str:
        """Вернуть осторожное описание породы и её происхождения."""

        prompt = (
            "Опиши собаку на изображении по-русски. Укажи предполагаемую породу "
            "или тип, заметные признаки и коротко происхождение породы. Если породу "
            "нельзя определить уверенно, прямо скажи, что это предположение. Ответ "
            "должен поместиться в подпись Telegram до 900 символов."
        )
        message = ChatMessage.from_user(
            content_parts=[prompt, ImageContent.from_url(image_url, detail="low")]
        )
        result = self._generator.run(messages=[message])
        caption = result["replies"][0].text.strip()
        if not caption:
            raise ExternalApiError("Модель не вернула описание изображения.")
        return caption[:900]


def build_agent_tools(
    *,
    weather_client: OpenMeteoClient,
    cat_client: CatFactClient,
    dog_client: DogImageClient,
    dog_analyzer: DogImageAnalyzer,
) -> list[Tool]:
    """Создать инструменты и привязать к ним внешние клиенты."""

    @tool
    def get_current_weather(
        city: Annotated[str, "Название города на русском или английском языке"],
    ) -> str:
        """Получить актуальную погоду в указанном городе."""

        logger.info("Инструмент get_current_weather: вызов")
        return format_weather(weather_client.get_current_weather(city))

    @tool
    def get_random_cat_fact() -> str:
        """Получить случайный факт о кошках из внешнего API."""

        logger.info("Инструмент get_random_cat_fact: вызов")
        return cat_client.get_random_fact()

    @tool(
        outputs_to_state={
            "dog_image_url": {"source": "image_url"},
            "dog_image_caption": {"source": "caption"},
        }
    )
    def get_and_analyze_dog_image() -> dict[str, str]:
        """Получить случайное изображение собаки и проанализировать его моделью."""

        logger.info("Инструмент get_and_analyze_dog_image: вызов")
        image_url = dog_client.get_random_image_url()
        caption = dog_analyzer.analyze(image_url)
        return {"image_url": image_url, "caption": caption}

    return [get_current_weather, get_random_cat_fact, get_and_analyze_dog_image]


def build_context_prompt(user_text: str, memories: list[str]) -> str:
    """Отделить найденную память от текущего сообщения пользователя."""

    if memories:
        context = "\n".join(f"- {text}" for text in memories)
    else:
        context = "Подходящих прошлых сообщений не найдено."
    return (
        "Контекст из Pinecone:\n"
        f"{context}\n\n"
        "Текущий запрос пользователя:\n"
        f"{user_text}"
    )


def select_tool_names(user_text: str) -> list[str]:
    """Разрешить только инструменты, явно запрошенные пользователем."""

    normalized = user_text.casefold().replace("ё", "е")
    selected: list[str] = []

    if re.search(r"\b(погод|температур|прогноз|осад|ветер)\w*", normalized):
        selected.append("get_current_weather")

    mentions_cat = re.search(r"\b(кош|кот)\w*", normalized)
    requests_fact = re.search(r"\bфакт\w*", normalized)
    if mentions_cat and requests_fact:
        selected.append("get_random_cat_fact")

    mentions_dog = re.search(r"\b(собак|пес|щен)\w*", normalized)
    requests_image = re.search(
        r"\b(покаж|изображ|картин|фото|сним|опиш|проанализ)\w*",
        normalized,
    )
    if mentions_dog and requests_image:
        selected.append("get_and_analyze_dog_image")

    return selected


class PersonalAssistantService:
    """Связать семантическую память, Haystack Agent и ответ Telegram."""

    def __init__(self, *, memory: ConversationMemory, agent: AgentRunner) -> None:
        self._memory = memory
        self._agent = agent

    def reply(self, *, user_id: int, message_id: int, text: str) -> AssistantReply:
        """Найти прошлый контекст, сохранить запрос и запустить агента."""

        normalized_text = text.strip()
        if not normalized_text:
            return AssistantReply(text="Напишите непустой вопрос.")

        memories: list[str] = []
        try:
            memories = self._memory.search(user_id, normalized_text)
        except Exception:
            logger.exception(
                "Не удалось получить контекст из Pinecone user_id_hash={}",
                _hash_id(user_id),
            )

        try:
            self._memory.save_user_message(user_id, message_id, normalized_text)
        except Exception:
            logger.exception(
                "Не удалось сохранить сообщение в Pinecone user_id_hash={}",
                _hash_id(user_id),
            )

        prompt = build_context_prompt(normalized_text, memories)
        allowed_tools = select_tool_names(normalized_text)
        result = self._agent.run(
            messages=[ChatMessage.from_user(prompt)],
            tools=allowed_tools,
        )
        answer = result["last_message"].text.strip()
        if not answer:
            answer = "Не удалось сформировать ответ. Попробуйте переформулировать вопрос."

        image_url = result.get("dog_image_url")
        image_caption = result.get("dog_image_caption")
        logger.info(
            "Ответ сформирован user_id_hash={} memories={} tool_calls={}",
            _hash_id(user_id),
            len(memories),
            result.get("tool_call_counts", {}),
        )
        return AssistantReply(
            text=answer,
            image_url=str(image_url) if image_url else None,
            image_caption=str(image_caption) if image_caption else None,
            tool_calls=dict(result.get("tool_call_counts", {})),
        )

    def memory_count(self, user_id: int) -> int:
        """Вернуть число сообщений в памяти пользователя."""

        return self._memory.count(user_id)

    def clear_memory(self, user_id: int) -> None:
        """Очистить память только текущего пользователя."""

        self._memory.clear(user_id)


def create_haystack_agent(
    *,
    chat_generator: OpenAIChatGenerator,
    tools: list[Tool],
) -> Agent:
    """Создать агента с явными инструментами и ограниченным числом шагов."""

    return Agent(
        chat_generator=chat_generator,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        state_schema={
            "dog_image_url": {"type": str},
            "dog_image_caption": {"type": str},
        },
        max_agent_steps=6,
        tool_concurrency_limit=1,
        raise_on_tool_invocation_failure=False,
    )


def _hash_id(value: int) -> str:
    """Скрыть Telegram ID в журнале событий."""

    import hashlib

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
