"""MCP server: weather_core exposed as tools, each UI tool linked to a ui:// view.

Protocol code only. Every tool is a thin wrapper around WeatherService that
returns:
- `content`: the core text summary (what the model reads, and what hosts
  without MCP Apps support display),
- `structuredContent`: the core model as JSON plus a `kind` discriminator
  (what the view renders).
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel
from weather_core import (
    ATTRIBUTION,
    MAX_FORECAST_DAYS,
    CityWeather,
    Forecast,
    HourlyForecast,
    Resolution,
    Units,
    WeatherError,
    WeatherService,
    create_service,
)

WEATHER_VIEW = "ui://weather/current.html"
FORECAST_VIEW = "ui://weather/forecast.html"
WORLD_CLOCK_VIEW = "ui://weather/world-clock.html"

VIEW_FILES = {
    WEATHER_VIEW: "current.html",
    FORECAST_VIEW: "forecast.html",
    WORLD_CLOCK_VIEW: "world-clock.html",
}

DEFAULT_VIEWS_DIR = Path(__file__).resolve().parents[3] / "views" / "dist"

INSTRUCTIONS = (
    "Weather, forecast and local time for cities, from Open-Meteo. "
    "When a city name is ambiguous the tools return candidates: the view lets "
    "the user pick one, or call the tool again with place_id."
)


def kind_of(model: BaseModel) -> str:
    if isinstance(model, Resolution):
        return "choose_place"
    if isinstance(model, CityWeather):
        return "weather"
    if isinstance(model, Forecast):
        return "forecast"
    if isinstance(model, HourlyForecast):
        return "hourly"
    raise TypeError(type(model).__name__)


def to_result(model: BaseModel, text: str) -> CallToolResult:
    structured: dict[str, Any] = {
        "kind": kind_of(model),
        **model.model_dump(mode="json"),
        "attribution": ATTRIBUTION.model_dump(),
    }
    return CallToolResult(
        content=[TextContent(type="text", text=text)], structured_content=structured
    )


def load_views(views_dir: Path) -> dict[str, str]:
    missing = [f for f in VIEW_FILES.values() if not (views_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Views not built in {views_dir} (missing {', '.join(missing)}). "
            "Run `make mcp-apps-views` first."
        )
    return {uri: (views_dir / f).read_text() for uri, f in VIEW_FILES.items()}


def build_server(
    service: WeatherService | None = None, views_dir: Path | None = None
) -> MCPServer:
    views_dir = views_dir or Path(
        os.environ.get("MCP_APPS_VIEWS_DIR", DEFAULT_VIEWS_DIR)
    )
    views = load_views(views_dir)
    svc = service or create_service()

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        yield
        await svc.client.aclose()

    apps = Apps()
    for uri, html in views.items():
        # Views are self-contained (inline JS/CSS, no network): the default,
        # strictest CSP applies, so no csp domains are declared.
        apps.add_html_resource(uri, html, name=VIEW_FILES[uri], prefers_border=True)

    @apps.tool(
        resource_uri=WEATHER_VIEW,
        title="Current weather",
        description=(
            "Current weather and local time for a city. Pass `city` (a name) or "
            "`place_id` (from a previous ambiguous result). Shows a weather card, "
            "or a picker when the name matches several places."
        ),
    )
    async def get_weather(
        city: str | None = None,
        place_id: int | None = None,
        units: Units = Units.METRIC,
    ) -> CallToolResult:
        try:
            result = await svc.city_weather(city, place_id, units)
        except WeatherError as exc:
            raise ToolError(str(exc)) from exc
        return to_result(result, result.summary)

    @apps.tool(
        resource_uri=FORECAST_VIEW,
        title="Daily forecast",
        description=(
            f"Daily forecast for one city, 1 to {MAX_FORECAST_DAYS} days (default 7): "
            "min/max temperature chart and precipitation bars. The user can change "
            "the number of days and the units in the view."
        ),
    )
    async def get_forecast(
        city: str | None = None,
        place_id: int | None = None,
        days: int = 7,
        units: Units = Units.METRIC,
    ) -> CallToolResult:
        try:
            result = await svc.forecast(city, place_id, days, units)
        except WeatherError as exc:
            raise ToolError(str(exc)) from exc
        return to_result(result, result.summary)

    @apps.tool(
        resource_uri=WORLD_CLOCK_VIEW,
        title="World clock",
        description=(
            "Local time and current weather for several cities at once (up to 8), "
            "shown as a grid of cards with live clocks."
        ),
    )
    async def get_world_clock(
        cities: list[str] | None = None,
        place_ids: list[int] | None = None,
        units: Units = Units.METRIC,
    ) -> CallToolResult:
        try:
            items = await svc.many_city_weather(cities, place_ids, units)
        except WeatherError as exc:
            raise ToolError(str(exc)) from exc
        structured = {
            "kind": "world_clock",
            "units": units.value,
            "items": [{"kind": kind_of(i), **i.model_dump(mode="json")} for i in items],
            "attribution": ATTRIBUTION.model_dump(),
        }
        text = "\n".join(i.summary for i in items)
        return CallToolResult(
            content=[TextContent(type="text", text=text)], structured_content=structured
        )

    server = MCPServer(
        "weather-mcp-apps",
        title="Weather (MCP Apps)",
        version="0.1.0",
        instructions=INSTRUCTIONS,
        extensions=[apps],
        lifespan=lifespan,
    )

    @server.tool(
        title="Hourly forecast",
        description="Hourly temperature and precipitation chance for the next 1 to 48 hours (text only, no view).",
    )
    async def get_hourly(
        city: str | None = None,
        place_id: int | None = None,
        hours: int = 24,
        units: Units = Units.METRIC,
    ) -> CallToolResult:
        try:
            result = await svc.hourly(city, place_id, hours, units)
        except WeatherError as exc:
            raise ToolError(str(exc)) from exc
        return to_result(result, result.summary)

    return server
