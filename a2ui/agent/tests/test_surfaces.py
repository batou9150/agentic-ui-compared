"""Every designed surface is valid A2UI 1.0, for the spec and for the SDK."""

from typing import Any

import pytest
from a2ui_agent import surfaces
from a2ui_agent.catalog import WEATHER_CATALOG_ID, validate
from a2ui_agent.surfaces import CreateMode
from weather_core import CityWeather, Forecast, Resolution, Units, WeatherService

from .spec import assert_spec_valid


def check(messages: list[dict[str, Any]]) -> None:
    assert_spec_valid(messages)
    validate(messages)  # the SDK's own renderer-side check


def components(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The layout, sent inline in createSurface or in updateComponents."""
    return [
        c
        for m in messages
        for key in ("createSurface", "updateComponents")
        for c in m.get(key, {}).get("components", [])
    ]


def data(messages: list[dict[str, Any]]) -> Any:
    """The root data model, sent inline in createSurface or in updateDataModel."""
    for m in messages:
        if "dataModel" in m.get("createSurface", {}):
            return m["createSurface"]["dataModel"]
        if m.get("updateDataModel", {}).get("path") == "/":
            return m["updateDataModel"]["value"]
    raise AssertionError("no data model")


def kinds(messages: list[dict[str, Any]]) -> list[str]:
    return [next(k for k in m if k != "version") for m in messages]


async def test_weather_card(service: WeatherService) -> None:
    w = await service.city_weather("Paris")
    assert isinstance(w, CityWeather)
    msgs = surfaces.weather_surface("weather-1", w)
    check(msgs)
    assert kinds(msgs) == ["createSurface"]  # inline: one message
    assert msgs[0]["createSurface"]["catalogId"] == WEATHER_CATALOG_ID
    assert sum(c["id"] == "root" for c in components(msgs)) == 1
    assert data(msgs)["place"].startswith("Paris")
    assert data(msgs)["localTime"] == "Local time 14:00 CEST"


async def test_split_mode_sends_the_same_surface_in_three_messages(
    service: WeatherService,
) -> None:
    w = await service.city_weather("Paris")
    assert isinstance(w, CityWeather)
    inline = surfaces.weather_surface("weather-1", w, mode=CreateMode.INLINE)
    split = surfaces.weather_surface("weather-1", w, mode=CreateMode.SPLIT)
    check(split)
    assert kinds(split) == ["createSurface", "updateComponents", "updateDataModel"]
    assert components(split) == components(inline)
    assert data(split) == data(inline)


def test_create_mode_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("A2UI_CREATE", raising=False)
    assert surfaces.create_mode() is CreateMode.INLINE
    monkeypatch.setenv("A2UI_CREATE", "split")
    assert surfaces.create_mode() is CreateMode.SPLIT


async def test_headings_are_markdown(service: WeatherService) -> None:
    w = await service.city_weather("Paris")
    assert isinstance(w, CityWeather)
    texts = [
        c
        for c in components(surfaces.weather_surface("w", w))
        if c["component"] == "Text"
    ]
    assert texts[0]["text"] == {
        "@call": "formatString",
        "args": {"value": "## ${/place}"},
    }
    assert {c.get("variant") for c in texts} <= {"body", "caption"}


async def test_picker_buttons_carry_place_ids(service: WeatherService) -> None:
    r = await service.resolve("Springfield")
    assert isinstance(r, Resolution)
    msgs = surfaces.picker_surface(
        "picker-1", r, then="forecast", units=Units.IMPERIAL, days=3
    )
    check(msgs)
    assert "dataModel" not in msgs[0]["createSurface"]  # literal values only
    buttons = [c for c in components(msgs) if c["component"] == "Button"]
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
    chart = data(msgs)["chart"]
    assert len(chart["labels"]) == days
    assert [s["kind"] for s in chart["series"]] == ["line", "line", "bar"]
    assert all(len(s["values"]) == days for s in chart["series"])


async def test_forecast_controls_only_send_data(service: WeatherService) -> None:
    f = await service.forecast("Lyon", days=16, units=Units.IMPERIAL)
    assert isinstance(f, Forecast)
    msgs = surfaces.forecast_update("forecast-1", f)
    assert kinds(msgs) == ["updateDataModel"]
    assert_spec_valid(msgs)
    layout = surfaces.forecast_layout().flatten()
    controls = [c for c in layout if c["component"] == "Button"]
    assert len(controls) == 5
    assert controls[0]["action"]["event"]["context"]["placeId"] == {"@path": "/placeId"}


async def test_redraw_in_place_never_creates(service: WeatherService) -> None:
    w = await service.city_weather("Paris")
    assert isinstance(w, CityWeather)
    msgs = surfaces.weather_surface("picker-1", w, create=False)
    check(msgs)
    assert kinds(msgs) == ["updateComponents", "updateDataModel"]


async def test_world_clock(service: WeatherService) -> None:
    items = await service.many_city_weather(
        ["Paris", "Tokyo", "New York", "Springfield"]
    )
    msgs = surfaces.world_clock_surface("clock-1", items)
    check(msgs)
    clocks = [c for c in components(msgs) if c["component"] == "Clock"]
    assert len(clocks) == 3
    cities = data(msgs)["cities"]
    assert cities[1]["timeZone"] == "Asia/Tokyo"
    assert "Several places match" in cities[3]["subtitle"]


def test_spec_validator_rejects_unknown_component() -> None:
    bad = {
        "version": "1.0",
        "updateComponents": {
            "surfaceId": "s",
            "components": [{"id": "root", "component": "Marquee", "text": "hi"}],
        },
    }
    with pytest.raises(AssertionError):
        assert_spec_valid([bad])


def test_spec_validator_rejects_v09_bindings() -> None:
    old = {
        "version": "1.0",
        "updateComponents": {
            "surfaceId": "s",
            "components": [{"id": "root", "component": "Text", "text": {"path": "/x"}}],
        },
    }
    with pytest.raises(AssertionError):
        assert_spec_valid([old])
