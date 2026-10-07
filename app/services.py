"""Сборка зависимостей приложения в одном месте."""

from __future__ import annotations

from haystack.components.embedders import OpenAIDocumentEmbedder, OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret

from app.agent_service import (
    DogImageAnalyzer,
    PersonalAssistantService,
    build_agent_tools,
    create_haystack_agent,
)
from app.config import Settings
from app.external_tools import CatFactClient, DogImageClient, OpenMeteoClient
from app.memory import PineconeConversationMemory


def build_assistant(settings: Settings) -> PersonalAssistantService:
    """Создать рабочий сервис с Haystack, Pinecone и внешними API."""

    proxy_secret = Secret.from_token(settings.proxyapi_key)
    generator_kwargs = {
        "api_key": proxy_secret,
        "model": settings.chat_model,
        "api_base_url": settings.proxyapi_base_url,
        "timeout": settings.http_timeout_seconds,
        "max_retries": 2,
    }
    chat_generator = OpenAIChatGenerator(
        **generator_kwargs,
        generation_kwargs={"temperature": 0.2},
    )
    vision_generator = OpenAIChatGenerator(
        **generator_kwargs,
        generation_kwargs={"temperature": 0.1},
    )

    document_embedder = OpenAIDocumentEmbedder(
        api_key=proxy_secret,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimension,
        api_base_url=settings.proxyapi_base_url,
        timeout=settings.http_timeout_seconds,
        max_retries=2,
        progress_bar=False,
        raise_on_failure=True,
    )
    text_embedder = OpenAITextEmbedder(
        api_key=proxy_secret,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimension,
        api_base_url=settings.proxyapi_base_url,
        timeout=settings.http_timeout_seconds,
        max_retries=2,
    )
    memory = PineconeConversationMemory(
        settings,
        document_embedder=document_embedder,
        text_embedder=text_embedder,
    )

    weather_client = OpenMeteoClient(timeout_seconds=settings.http_timeout_seconds)
    cat_client = CatFactClient(timeout_seconds=settings.http_timeout_seconds)
    dog_client = DogImageClient(timeout_seconds=settings.http_timeout_seconds)
    dog_analyzer = DogImageAnalyzer(vision_generator)
    tools = build_agent_tools(
        weather_client=weather_client,
        cat_client=cat_client,
        dog_client=dog_client,
        dog_analyzer=dog_analyzer,
    )
    agent = create_haystack_agent(chat_generator=chat_generator, tools=tools)
    return PersonalAssistantService(memory=memory, agent=agent)

