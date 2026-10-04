"""Every designed surface is valid A2UI v0.9.1, for the spec and for the SDK."""

from typing import Any

import pytest
from a2ui_agent import surfaces
from a2ui_agent.catalog import WEATHER_CATALOG_ID, weather_catalog
from weather_core import CityWeather, Forecast, Resolution, Units, WeatherService

from .spec import assert_spec_valid


def check(messages: list[dict[str, Any]]) -> None:
    assert_spec_valid(messages)
    weather_catalog().validate(messages)  # the SDK's own processor, strict mode


async def test_weather_card(service: WeatherService) -> None:
    w = await service.city_weather("Paris")
    assert isinstance(w, CityWeather)
    msgs = surfaces.weather_surface("weather-1", w)
    check(msgs)
    assert msgs[0]["createSurface"]["catalogId"] == WEATHER_CATALOG_ID
    comps = msgs[1]["updateComponents"]["components"]
    assert sum(c["id"] == "root" for c in comps) == 1
    data = msgs[2]["updateDataModel"]["value"]
    assert data["place"].startswith("Paris")
    assert data["localTime"] == "Local time 14:00 CEST"


async def test_picker_buttons_carry_place_ids(service: WeatherService) -> None:
    r = await service.resolve("Springfield")
    assert isinstance(r, Resolution)
    msgs = surfaces.picker_surface(
        "picker-1", r, then="forecast", units=Units.IMPERIAL, days=3
    )
    check(msgs)
    buttons = [
        c
        for c in msgs[1]["updateComponents"]["components"]
        if c["component"] == "Button"
    ]
    assert len(buttons) == 5
    ctx = buttons[2]["action"]["event"]["context"]
    assert ctx == {
        "placeId": 4250542,
        "then": "forecast",
        "units": "imperial",
        "days": 3,
    }


@pytest.mark.parametrize("days", [3, 7, 16])
async def test_forecast_chart(service: WeatherService, days: int) -> None:
    f = await service.forecast("Lyon", days=days)
    assert isinstance(f, Forecast)
    msgs = surfaces.forecast_surface("forecast-1", f)
    check(msgs)
    chart = msgs[2]["updateDataModel"]["value"]["chart"]
    assert len(chart["labels"]) == days
    assert [s["kind"] for s in chart["series"]] == ["line", "line", "bar"]
    assert all(len(s["values"]) == days for s in chart["series"])


async def test_forecast_controls_only_send_data(service: WeatherService) -> None:
    f = await service.forecast("Lyon", days=16, units=Units.IMPERIAL)
    assert isinstance(f, Forecast)
    msgs = surfaces.forecast_update("forecast-1", f)
    assert [list(m)[1] for m in msgs] == ["updateDataModel"]
    assert_spec_valid(msgs)
    layout = surfaces.forecast_layout().flatten()
    controls = [c for c in layout if c["component"] == "Button"]
    assert len(controls) == 5
    assert controls[0]["action"]["event"]["context"]["placeId"] == {"path": "/placeId"}


async def test_world_clock(service: WeatherService) -> None:
    items = await service.many_city_weather(
        ["Paris", "Tokyo", "New York", "Springfield"]
    )
    msgs = surfaces.world_clock_surface("clock-1", items)
    check(msgs)
    clocks = [
        c
        for c in msgs[1]["updateComponents"]["components"]
        if c["component"] == "Clock"
    ]
    assert len(clocks) == 3
    cities = msgs[2]["updateDataModel"]["value"]["cities"]
    assert cities[1]["timeZone"] == "Asia/Tokyo"
    assert "Several places match" in cities[3]["subtitle"]


def test_spec_validator_rejects_unknown_component() -> None:
    bad = {
        "version": "v0.9.1",
        "updateComponents": {
            "surfaceId": "s",
            "components": [{"id": "root", "component": "Marquee", "text": "hi"}],
        },
    }
    with pytest.raises(AssertionError):
        assert_spec_valid([bad])
