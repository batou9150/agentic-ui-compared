"""ADK tools over weather_core, shared by Live (LLM) and Scripted (no LLM) modes.

A tool returns the core text summary to the model. When `show_ui` is true it
also queues its core model on UI_SINK; the executor turns queued models into
designed A2UI surfaces (surfaces.py). This mirrors MCP Apps, where the model
reads `content` and the view reads `structuredContent`.
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from weather_core import (
    CityWeather,
    Forecast,
    HourlyForecast,
    InvalidRequestError,
    Resolution,
    Units,
    WeatherError,
    WeatherService,
)


@dataclass
class UiRequest:
    """A tool result that should be rendered with a designed surface."""

    tool: str
    result: Any  # CityWeather | Resolution | Forecast | list[CityWeather | Resolution]
    args: dict[str, Any] = field(default_factory=dict)


UI_SINK: ContextVar[list[UiRequest] | None] = ContextVar("UI_SINK", default=None)

Tool = Callable[..., Awaitable[dict[str, Any]]]


def _emit(tool: str, result: Any, args: dict[str, Any]) -> None:
    sink = UI_SINK.get()
    if sink is not None:
        sink.append(UiRequest(tool, result, args))


def _reply(
    result: BaseModel | list[Any], summary: str, show_ui: bool
) -> dict[str, Any]:
    reply: dict[str, Any] = {
        "status": "success",
        "summary": summary,
        "ui_shown": show_ui,
    }
    if not show_ui:  # the model composes its own UI and needs the numbers
        if isinstance(result, list):
            reply["data"] = [r.model_dump(mode="json") for r in result]
        else:
            reply["data"] = result.model_dump(mode="json")
    return reply


def _error(exc: WeatherError) -> dict[str, Any]:
    return {"status": "error", "error_message": str(exc)}


def _units(value: str) -> Units:
    # The LLM may send "celsius" or "F"; answer with a tool error, not a crash.
    try:
        return Units(value)
    except ValueError:
        raise InvalidRequestError(
            f'Unknown units \'{value}\'. Use "metric" or "imperial".'
        ) from None


def make_tools(service: WeatherService) -> dict[str, Tool]:
    async def get_weather(
        city: str | None = None,
        place_id: int | None = None,
        units: str = "metric",
        show_ui: bool = True,
    ) -> dict[str, Any]:
        """Current weather and local time for one city, shown as a weather card.

        Args:
            city: City name, e.g. "Paris". Omit when place_id is given.
            place_id: Id of a place from a previous ambiguous result.
            units: "metric" (°C) or "imperial" (°F).
            show_ui: Render the designed weather card (default). Set to false only
                when you will compose your own A2UI layout from the returned data.
        """
        try:
            result = await service.city_weather(city, place_id, _units(units))
        except WeatherError as exc:
            return _error(exc)
        if show_ui:
            _emit("get_weather", result, {"units": units})
        return _reply(result, result.summary, show_ui)

    async def get_forecast(
        city: str | None = None,
        place_id: int | None = None,
        days: int = 7,
        units: str = "metric",
        show_ui: bool = True,
    ) -> dict[str, Any]:
        """Daily forecast (1 to 16 days) for one city, shown as a chart with controls.

        Args:
            city: City name, e.g. "Lyon". Omit when place_id is given.
            place_id: Id of a place from a previous ambiguous result.
            days: Number of days, 1 to 16 (default 7).
            units: "metric" (°C) or "imperial" (°F).
            show_ui: Render the designed forecast chart (default). Set to false
                only when you will compose your own A2UI layout from the data.
        """
        try:
            result = await service.forecast(city, place_id, days, _units(units))
        except WeatherError as exc:
            return _error(exc)
        if show_ui:
            _emit("get_forecast", result, {"units": units, "days": days})
        return _reply(result, result.summary, show_ui)

    async def get_world_clock(
        cities: list[str],
        units: str = "metric",
        show_ui: bool = True,
    ) -> dict[str, Any]:
        """Local time and current weather for several cities (up to 8), as a grid of live clocks.

        Args:
            cities: City names, e.g. ["Paris", "Tokyo", "New York"].
            units: "metric" (°C) or "imperial" (°F).
            show_ui: Render the designed world clock grid (default).
        """
        try:
            items = await service.many_city_weather(cities, None, _units(units))
        except WeatherError as exc:
            return _error(exc)
        if show_ui:
            _emit("get_world_clock", items, {"units": units})
        return _reply(items, "\n".join(i.summary for i in items), show_ui)

    async def get_hourly(
        city: str | None = None,
        place_id: int | None = None,
        hours: int = 24,
        units: str = "metric",
    ) -> dict[str, Any]:
        """Hourly temperature and precipitation chance for the next 1 to 48 hours (data only, no designed UI).

        Args:
            city: City name. Omit when place_id is given.
            place_id: Id of a place from a previous ambiguous result.
            hours: Number of hours, 1 to 48 (default 24).
            units: "metric" (°C) or "imperial" (°F).
        """
        try:
            result: HourlyForecast | Resolution = await service.hourly(
                city, place_id, hours, _units(units)
            )
        except WeatherError as exc:
            return _error(exc)
        return _reply(result, result.summary, show_ui=False)

    return {
        "get_weather": get_weather,
        "get_forecast": get_forecast,
        "get_world_clock": get_world_clock,
        "get_hourly": get_hourly,
    }


__all__ = ["UI_SINK", "CityWeather", "Forecast", "UiRequest", "make_tools"]
