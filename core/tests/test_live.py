"""Opt-in smoke test against the real API, to detect drift: pytest -m live."""

import pytest
from weather_core import CityWeather, Forecast, OpenMeteoClient, WeatherService

pytestmark = pytest.mark.live


async def test_live_paris_end_to_end() -> None:
    service = WeatherService(OpenMeteoClient())
    weather = await service.city_weather("Paris")
    forecast = await service.forecast("Paris", days=16)
    assert isinstance(weather, CityWeather) and isinstance(forecast, Forecast)
    assert len(forecast.daily) == 16
    resolution = await service.resolve("Springfield")
    assert resolution.ambiguous
    await service.client.aclose()
