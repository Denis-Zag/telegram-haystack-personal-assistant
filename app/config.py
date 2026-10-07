"""Настройки приложения из переменных окружения."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Проверенные настройки бота и внешних сервисов."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str = Field(min_length=10)
    proxyapi_key: str = Field(min_length=10)
    pinecone_api_key: str = Field(min_length=10)

    proxyapi_base_url: str = "https://api.proxyapi.ru/v1"
    chat_model: str = "openai/gpt-4o-mini"
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimension: PositiveInt = 1536

    pinecone_index: str = "telegram-haystack-assistant"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    memory_top_k: PositiveInt = 5

    http_timeout_seconds: PositiveFloat = 15.0
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Загрузить настройки один раз за время работы процесса."""

    return Settings()  # type: ignore[call-arg]

