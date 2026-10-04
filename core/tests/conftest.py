from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from weather_core import FixtureTransport, OpenMeteoClient, WeatherService

# 2026-10-04 12:00 UTC: summer time in Paris and New York, none in Tokyo.
FROZEN_NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def transport() -> FixtureTransport:
    return FixtureTransport()


@pytest.fixture
async def service(transport: FixtureTransport) -> AsyncIterator[WeatherService]:
    client = OpenMeteoClient(transport=transport)
    yield WeatherService(client, clock=lambda: FROZEN_NOW)
    await client.aclose()
