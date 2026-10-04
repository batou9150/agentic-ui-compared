"""Protocol-level checks: tools, _meta.ui links, ui:// resources, results."""

from pathlib import Path
from typing import Any

import pytest
from mcp.server.apps import APP_MIME_TYPE
from mcp_apps_server import build_server
from mcp_apps_server.server import FORECAST_VIEW, WEATHER_VIEW, WORLD_CLOCK_VIEW

from .conftest import Connect

UI_TOOLS = {
    "get_weather": WEATHER_VIEW,
    "get_forecast": FORECAST_VIEW,
    "get_world_clock": WORLD_CLOCK_VIEW,
}


async def test_tools_are_listed_with_ui_links(connect: Connect) -> None:
    async with connect() as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert set(tools) == {*UI_TOOLS, "get_hourly"}
        for name, uri in UI_TOOLS.items():
            meta = tools[name].meta or {}
            assert meta["ui"]["resourceUri"] == uri
            assert "ui/resourceUri" not in meta  # deprecated flat key not emitted
        assert "ui" not in (tools["get_hourly"].meta or {})


async def test_every_ui_link_resolves_to_an_app_resource(connect: Connect) -> None:
    async with connect() as client:
        listed = {str(r.uri): r for r in (await client.list_resources()).resources}
        for uri in UI_TOOLS.values():
            assert listed[uri].mime_type == APP_MIME_TYPE
            read = await client.read_resource(uri)
            content = read.contents[0]
            assert content.mime_type == APP_MIME_TYPE
            assert getattr(content, "text", "").startswith("<!doctype html>")


def _structured(result: Any) -> dict[str, Any]:
    assert not result.is_error, result.content
    data: dict[str, Any] = result.structured_content
    assert data["attribution"]["text"] == "Weather data by Open-Meteo.com"
    return data


async def test_get_weather_returns_card_data_and_text(connect: Connect) -> None:
    async with connect() as client:
        result = await client.call_tool("get_weather", {"city": "Paris"})
        data = _structured(result)
        assert data["kind"] == "weather"
        assert data["place"]["country_code"] == "FR"
        assert result.content[0].text == data["summary"]


async def test_ambiguous_city_returns_candidates(connect: Connect) -> None:
    async with connect() as client:
        data = _structured(
            await client.call_tool("get_weather", {"city": "Springfield"})
        )
        assert data["kind"] == "choose_place"
        assert len(data["candidates"]) == 5


async def test_pick_by_place_id(connect: Connect) -> None:
    async with connect() as client:
        data = _structured(
            await client.call_tool(
                "get_weather", {"place_id": 4250542, "units": "imperial"}
            )
        )
        assert data["kind"] == "weather"
        assert data["place"]["region"] == "Illinois"
        assert data["unit_labels"]["temperature"] == "°F"


@pytest.mark.parametrize("days", [3, 7, 16])
async def test_forecast_days(connect: Connect, days: int) -> None:
    async with connect() as client:
        data = _structured(
            await client.call_tool("get_forecast", {"city": "Lyon", "days": days})
        )
        assert data["kind"] == "forecast"
        assert len(data["daily"]) == days


async def test_world_clock(connect: Connect) -> None:
    async with connect() as client:
        data = _structured(
            await client.call_tool(
                "get_world_clock", {"cities": ["Paris", "Tokyo", "New York"]}
            )
        )
        assert data["kind"] == "world_clock"
        assert [i["place"]["name"] for i in data["items"]] == [
            "Paris",
            "Tokyo",
            "New York",
        ]


async def test_hourly_is_text_only_tool(connect: Connect) -> None:
    async with connect() as client:
        data = _structured(
            await client.call_tool("get_hourly", {"city": "Tokyo", "hours": 12})
        )
        assert len(data["hourly"]) == 12


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("get_weather", {"city": "Zzzqqx"}, "No location found"),
        ("get_forecast", {"city": "Lyon", "days": 20}, "between 1 and 16"),
        ("get_weather", {}, "city name or a place id"),
        ("get_world_clock", {"cities": []}, "at least one city"),
    ],
)
async def test_domain_errors_become_tool_errors(
    connect: Connect, tool: str, args: dict[str, Any], message: str
) -> None:
    async with connect() as client:
        result = await client.call_tool(tool, args)
        assert result.is_error
        assert message in result.content[0].text


def test_missing_views_fail_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make mcp-apps-views"):
        build_server(views_dir=tmp_path)
