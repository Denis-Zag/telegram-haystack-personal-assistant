"""Проверки регистрации и результатов инструментов агента."""

from __future__ import annotations

from app.agent_service import build_agent_tools
from app.models import WeatherResult


class FakeWeather:
    def get_current_weather(self, city: str) -> WeatherResult:
        return WeatherResult(city, "Россия", 10, 8, 5, 0, "ясно")


class FakeCat:
    def get_random_fact(self) -> str:
        return "Кошки спят большую часть суток."


class FakeDog:
    def get_random_image_url(self) -> str:
        return "https://images.example/dog.jpg"


class FakeAnalyzer:
    def analyze(self, image_url: str) -> str:
        assert image_url == "https://images.example/dog.jpg"
        return "Предположительно лабрадор."


def test_tools_have_required_names_and_results() -> None:
    tools = build_agent_tools(
        weather_client=FakeWeather(),  # type: ignore[arg-type]
        cat_client=FakeCat(),  # type: ignore[arg-type]
        dog_client=FakeDog(),  # type: ignore[arg-type]
        dog_analyzer=FakeAnalyzer(),  # type: ignore[arg-type]
    )
    by_name = {registered_tool.name: registered_tool for registered_tool in tools}

    assert set(by_name) == {
        "get_current_weather",
        "get_random_cat_fact",
        "get_and_analyze_dog_image",
    }
    assert "10 °C" in by_name["get_current_weather"].function("Москва")
    assert "Кошки" in by_name["get_random_cat_fact"].function()
    assert by_name["get_and_analyze_dog_image"].function() == {
        "image_url": "https://images.example/dog.jpg",
        "caption": "Предположительно лабрадор.",
    }


def test_dog_tool_maps_image_and_caption_to_agent_state() -> None:
    dog_tool = build_agent_tools(
        weather_client=FakeWeather(),  # type: ignore[arg-type]
        cat_client=FakeCat(),  # type: ignore[arg-type]
        dog_client=FakeDog(),  # type: ignore[arg-type]
        dog_analyzer=FakeAnalyzer(),  # type: ignore[arg-type]
    )[2]

    assert dog_tool.outputs_to_state == {
        "dog_image_url": {"source": "image_url"},
        "dog_image_caption": {"source": "caption"},
    }

