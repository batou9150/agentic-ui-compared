import pytest
from weather_core import (
    CityWeather,
    Forecast,
    HourlyForecast,
    InvalidRequestError,
    Resolution,
    Units,
    WeatherService,
)


async def test_city_weather_paris(service: WeatherService) -> None:
    w = await service.city_weather("Paris")
    assert isinstance(w, CityWeather)
    assert w.unit_labels.temperature == "°C"
    assert 0 <= w.current.humidity <= 100
    assert w.current.condition.icon
    assert w.local_time.timezone == "Europe/Paris"
    assert w.local_time.iso.hour == 14  # 12:00 UTC is 14:00 CEST
    assert w.local_time.utc_offset_seconds == 7200
    assert "Paris" in w.summary and "°C" in w.summary


async def test_imperial_is_converted_locally(
    service: WeatherService, transport
) -> None:  # type: ignore[no-untyped-def]
    metric = await service.city_weather("Paris")
    sent = len(transport.requests)
    imperial = await service.city_weather("Paris", units=Units.IMPERIAL)
    assert isinstance(metric, CityWeather) and isinstance(imperial, CityWeather)
    assert len(transport.requests) == sent  # served from cache, no new call
    assert imperial.current.temperature == pytest.approx(
        metric.current.temperature * 9 / 5 + 32, abs=0.11
    )
    assert imperial.unit_labels.wind_speed == "mph"


async def test_city_weather_ambiguous_returns_resolution(
    service: WeatherService,
) -> None:
    w = await service.city_weather("Springfield")
    assert isinstance(w, Resolution) and w.ambiguous


async def test_city_weather_by_place_id(service: WeatherService) -> None:
    w = await service.city_weather(place_id=4250542)
    assert isinstance(w, CityWeather)
    assert w.place.region == "Illinois"
    assert w.local_time.abbreviation == "CDT"


async def test_tokyo_local_time(service: WeatherService) -> None:
    w = await service.city_weather("Tokyo")
    assert isinstance(w, CityWeather)
    assert (w.local_time.iso.hour, w.local_time.utc_offset_seconds) == (21, 9 * 3600)


@pytest.mark.parametrize("days", [1, 3, 7, 16])
async def test_forecast_lengths(service: WeatherService, days: int) -> None:
    f = await service.forecast("Lyon", days=days)
    assert isinstance(f, Forecast)
    assert len(f.daily) == f.days == days
    for p in f.daily:
        assert p.temperature_min <= p.temperature_max
        assert p.precipitation_sum >= 0
    assert f.summary.count("\n") == days


async def test_forecast_days_hit_one_cached_call(
    service: WeatherService, transport
) -> None:  # type: ignore[no-untyped-def]
    await service.forecast("Lyon", days=3)
    sent = len(transport.requests)
    await service.forecast("Lyon", days=16, units=Units.IMPERIAL)
    assert len(transport.requests) == sent


@pytest.mark.parametrize("days", [0, 17, -1])
async def test_forecast_rejects_bad_days(service: WeatherService, days: int) -> None:
    with pytest.raises(InvalidRequestError):
        await service.forecast("Lyon", days=days)


async def test_forecast_imperial_precipitation(service: WeatherService) -> None:
    metric = await service.forecast("Lyon", days=16)
    imperial = await service.forecast("Lyon", days=16, units=Units.IMPERIAL)
    assert isinstance(metric, Forecast) and isinstance(imperial, Forecast)
    for m, i in zip(metric.daily, imperial.daily, strict=True):
        assert i.precipitation_sum == pytest.approx(
            m.precipitation_sum / 25.4, abs=0.01
        )
    assert imperial.unit_labels.precipitation == "in"


async def test_forecast_ambiguous(service: WeatherService) -> None:
    assert isinstance(await service.forecast("Springfield"), Resolution)


async def test_hourly(service: WeatherService) -> None:
    h = await service.hourly("New York", hours=24)
    assert isinstance(h, HourlyForecast)
    assert len(h.hourly) == 24
    assert "New York" in h.summary
    with pytest.raises(InvalidRequestError):
        await service.hourly("New York", hours=49)
    assert isinstance(await service.hourly("Springfield"), Resolution)


async def test_models_serialise_to_json(service: WeatherService) -> None:
    w = await service.city_weather("Paris")
    data = w.model_dump(mode="json")
    assert data["current"]["condition"]["icon"]
    assert data["local_time"]["iso"].endswith("+02:00")
