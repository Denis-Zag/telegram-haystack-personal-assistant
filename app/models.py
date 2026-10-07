"""Внутренние модели данных приложения."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WeatherResult:
    """Нормализованная текущая погода для найденного города."""

    location: str
    country: str
    temperature: float
    apparent_temperature: float
    wind_speed: float
    precipitation: float
    description: str


@dataclass(frozen=True, slots=True)
class DogImageResult:
    """Ссылка на изображение собаки и результат анализа модели."""

    image_url: str
    caption: str


@dataclass(frozen=True, slots=True)
class AssistantReply:
    """Ответ ассистента для отправки в Telegram."""

    text: str
    image_url: str | None = None
    image_caption: str | None = None
    tool_calls: dict[str, int] = field(default_factory=dict)
