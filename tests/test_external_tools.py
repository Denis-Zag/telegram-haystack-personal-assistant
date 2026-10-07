"""Офлайн-проверки внешних API-клиентов."""

from __future__ import annotations

import httpx
import pytest

from app.external_tools import (
    CatFactClient,
    DogImageClient,
    ExternalApiError,
    OpenMeteoClient,
    format_weather,
)


def test_weather_combines_geocoding_and_forecast() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Москва",
                            "country": "Россия",
                            "latitude": 55.75,
                            "longitude": 37.62,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": 8.0,
                    "apparent_temperature": 5.2,
                    "precipitation": 0.0,
                    "weather_code": 2,
                    "wind_speed_10m": 12.0,
                }
            },
        )

    client = OpenMeteoClient(
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    result = client.get_current_weather("Москва")

    assert requests == ["geocoding-api.open-meteo.com", "api.open-meteo.com"]
    assert "Москва, Россия" in format_weather(result)
    assert "8 °C" in format_weather(result)


def test_weather_rejects_unknown_city() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"results": []}))
    client = OpenMeteoClient(timeout_seconds=5, transport=transport)

    with pytest.raises(ExternalApiError, match="Город не найден"):
        client.get_current_weather("Несуществующий город")


def test_cat_fact_returns_text() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"fact": "Cats sleep a lot."})
    )
    client = CatFactClient(timeout_seconds=5, transport=transport)

    assert client.get_random_fact() == "Cats sleep a lot."


def test_dog_image_requires_successful_https_url() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"status": "success", "message": "https://images.example/dog.jpg"},
        )
    )
    client = DogImageClient(timeout_seconds=5, transport=transport)

    assert client.get_random_image_url() == "https://images.example/dog.jpg"


def test_dog_image_rejects_insecure_url() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"status": "success", "message": "http://images.example/dog.jpg"},
        )
    )
    client = DogImageClient(timeout_seconds=5, transport=transport)

    with pytest.raises(ExternalApiError, match="некорректную ссылку"):
        client.get_random_image_url()

