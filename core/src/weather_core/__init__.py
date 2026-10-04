"""Weather and local time domain shared by the MCP Apps and A2UI implementations."""

import os
from datetime import UTC, datetime

from .client import MAX_FORECAST_DAYS, OpenMeteoClient
from .errors import InvalidRequestError, PlaceNotFoundError, UpstreamError, WeatherError
from .fixtures import FixtureTransport
from .models import (
    ATTRIBUTION,
    Attribution,
    CityWeather,
    Condition,
    CurrentConditions,
    DailyPoint,
    Forecast,
    HourlyForecast,
    HourlyPoint,
    LocalTime,
    Place,
    Resolution,
    UnitLabels,
    Units,
)
from .service import WeatherService

__all__ = [
    "ATTRIBUTION",
    "MAX_FORECAST_DAYS",
    "Attribution",
    "CityWeather",
    "Condition",
    "CurrentConditions",
    "DailyPoint",
    "FixtureTransport",
    "Forecast",
    "HourlyForecast",
    "HourlyPoint",
    "InvalidRequestError",
    "LocalTime",
    "OpenMeteoClient",
    "Place",
    "PlaceNotFoundError",
    "Resolution",
    "UnitLabels",
    "Units",
    "UpstreamError",
    "WeatherError",
    "WeatherService",
    "create_service",
]


def create_service() -> WeatherService:
    """Build the service from the environment (see .env.example).

    OPEN_METEO_MODE      live (default) or fixtures (offline, deterministic)
    OPEN_METEO_CACHE_TTL cache lifetime in seconds (default 600)
    WEATHER_FIXED_NOW    ISO datetime to freeze "now" (Scripted mode, tests)
    """
    mode = os.environ.get("OPEN_METEO_MODE", "live").strip().lower()
    if mode not in ("live", "fixtures"):
        raise ValueError(f"OPEN_METEO_MODE must be 'live' or 'fixtures', not {mode!r}")
    ttl = float(os.environ.get("OPEN_METEO_CACHE_TTL", "600"))
    transport = FixtureTransport() if mode == "fixtures" else None
    client = OpenMeteoClient(transport=transport, cache_ttl=ttl)
    fixed = os.environ.get("WEATHER_FIXED_NOW")
    if fixed:
        frozen = datetime.fromisoformat(fixed)
        if frozen.tzinfo is None:
            frozen = frozen.replace(tzinfo=UTC)
        return WeatherService(client, clock=lambda: frozen)
    return WeatherService(client)
