from datetime import UTC, datetime

import pytest
from weather_core import FixtureTransport, OpenMeteoClient, WeatherService

FROZEN_NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def service() -> WeatherService:
    return WeatherService(
        OpenMeteoClient(transport=FixtureTransport()), clock=lambda: FROZEN_NOW
    )
