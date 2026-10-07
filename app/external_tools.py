"""Клиенты внешних API для инструментов Haystack-агента."""

from __future__ import annotations

from typing import Any

import httpx

from app.models import WeatherResult


class ExternalApiError(RuntimeError):
    """Понятная ошибка внешнего API без технических деталей для пользователя."""


WEATHER_DESCRIPTIONS = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозевый туман",
    51: "лёгкая морось",
    53: "морось",
    55: "сильная морось",
    61: "небольшой дождь",
    63: "дождь",
    65: "сильный дождь",
    71: "небольшой снег",
    73: "снег",
    75: "сильный снег",
    80: "небольшой ливень",
    81: "ливень",
    82: "сильный ливень",
    95: "гроза",
    96: "гроза с небольшим градом",
    99: "гроза с сильным градом",
}


class OpenMeteoClient:
    """Найти город и получить его текущую погоду через Open-Meteo."""

    geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"
    forecast_url = "https://api.open-meteo.com/v1/forecast"

    def __init__(
        self,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def get_current_weather(self, city: str) -> WeatherResult:
        """Вернуть текущую погоду для первого результата геокодинга."""

        normalized_city = city.strip()
        if len(normalized_city) < 2:
            raise ExternalApiError("Укажите название города.")

        try:
            with self._client() as client:
                location_response = client.get(
                    self.geocoding_url,
                    params={
                        "name": normalized_city,
                        "count": 1,
                        "language": "ru",
                        "format": "json",
                    },
                )
                location_response.raise_for_status()
                locations = location_response.json().get("results") or []
                if not locations:
                    raise ExternalApiError("Город не найден.")
                location = locations[0]

                weather_response = client.get(
                    self.forecast_url,
                    params={
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "current": (
                            "temperature_2m,apparent_temperature,precipitation,"
                            "weather_code,wind_speed_10m"
                        ),
                        "timezone": "auto",
                    },
                )
                weather_response.raise_for_status()
                current = weather_response.json()["current"]
        except ExternalApiError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ExternalApiError("Не удалось получить погоду от Open-Meteo.") from error

        weather_code = int(current.get("weather_code", -1))
        return WeatherResult(
            location=str(location.get("name", normalized_city)),
            country=str(location.get("country", "")),
            temperature=float(current["temperature_2m"]),
            apparent_temperature=float(current["apparent_temperature"]),
            wind_speed=float(current["wind_speed_10m"]),
            precipitation=float(current["precipitation"]),
            description=WEATHER_DESCRIPTIONS.get(weather_code, "условия без описания"),
        )

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout_seconds, transport=self._transport)


class CatFactClient:
    """Получить случайный факт о кошках."""

    url = "https://catfact.ninja/fact"

    def __init__(
        self,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def get_random_fact(self) -> str:
        """Вернуть непустой текст факта."""

        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.get(self.url)
                response.raise_for_status()
                fact = str(response.json()["fact"]).strip()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ExternalApiError("Не удалось получить факт о кошках.") from error
        if not fact:
            raise ExternalApiError("Сервис вернул пустой факт о кошках.")
        return fact


class DogImageClient:
    """Получить ссылку на случайное изображение собаки."""

    url = "https://dog.ceo/api/breeds/image/random"

    def __init__(
        self,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def get_random_image_url(self) -> str:
        """Вернуть проверенную HTTPS-ссылку из Dog CEO API."""

        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.get(self.url)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                image_url = str(payload["message"]).strip()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ExternalApiError("Не удалось получить изображение собаки.") from error

        if payload.get("status") != "success" or not image_url.startswith("https://"):
            raise ExternalApiError("Сервис вернул некорректную ссылку на изображение.")
        return image_url


def format_weather(result: WeatherResult) -> str:
    """Сформировать компактный результат погодного инструмента."""

    place = result.location
    if result.country:
        place += f", {result.country}"
    return (
        f"Текущая погода: {place}. {result.description.capitalize()}. "
        f"Температура {result.temperature:g} °C, ощущается как "
        f"{result.apparent_temperature:g} °C. Ветер {result.wind_speed:g} км/ч, "
        f"осадки {result.precipitation:g} мм."
    )
