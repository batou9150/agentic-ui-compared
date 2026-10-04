from datetime import UTC

import pytest
from weather_core import CityWeather, FixtureTransport, UpstreamError, create_service


async def test_fixture_mode_with_frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_METEO_MODE", "fixtures")
    monkeypatch.setenv("WEATHER_FIXED_NOW", "2026-10-04T12:00:00")
    service = create_service()
    w = await service.city_weather("Tokyo")
    assert isinstance(w, CityWeather)
    assert w.local_time.iso.astimezone(UTC).hour == 12
    await service.client.aclose()


def test_rejects_unknown_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_METEO_MODE", "replay")
    with pytest.raises(ValueError, match="OPEN_METEO_MODE"):
        create_service()


def test_live_mode_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPEN_METEO_MODE", raising=False)
    monkeypatch.delenv("WEATHER_FIXED_NOW", raising=False)
    service = create_service()
    assert not isinstance(service.client._http._transport, FixtureTransport)


async def test_missing_fixture_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_METEO_MODE", "fixtures")
    service = create_service()
    with pytest.raises(UpstreamError, match="No recorded fixture"):
        await service.resolve("Atlantis")
    await service.client.aclose()
