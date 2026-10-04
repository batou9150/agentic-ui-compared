"""Thin async client for the Open-Meteo APIs, with a short in-memory TTL cache.

Open-Meteo is free for non-commercial use and asks for reasonable volume, so
every response is cached for `cache_ttl` seconds (10 minutes by default).
The client always fetches metric values; unit conversion happens in
`service.py` so that switching °C/°F never triggers a new API call.
"""

import time
from typing import Any

import httpx

from .errors import UpstreamError

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
GEOCODING_GET_URL = "https://geocoding-api.open-meteo.com/v1/get"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

MAX_FORECAST_DAYS = 16
HOURLY_HOURS = 48

CURRENT_FIELDS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
    "wind_speed_10m,wind_direction_10m,is_day"
)
HOURLY_FIELDS = "temperature_2m,precipitation_probability,weather_code"
DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "precipitation_probability_max,sunrise,sunset"
)

JSON = dict[str, Any]


class OpenMeteoClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
        cache_ttl: float = 600.0,
        clock: Any = time.monotonic,
    ) -> None:
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "agentic-ui-compared (demo, non-commercial)"},
        )
        self._ttl = cache_ttl
        self._clock = clock
        self._cache: dict[
            tuple[str, tuple[tuple[str, str], ...]], tuple[float, JSON]
        ] = {}
        self.requests_sent = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, url: str, params: dict[str, Any]) -> JSON:
        key = (url, tuple(sorted((k, str(v)) for k, v in params.items())))
        now = self._clock()
        hit = self._cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
        try:
            response = await self._http.get(url, params=params)
            self.requests_sent += 1
            response.raise_for_status()
            data: JSON = response.json()
        except httpx.HTTPStatusError as exc:
            reason = _error_reason(exc.response)
            raise UpstreamError(
                f"Open-Meteo answered {exc.response.status_code}: {reason}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamError(f"Open-Meteo is unavailable: {exc}") from exc
        self._cache[key] = (now + self._ttl, data)
        return data

    async def search(self, name: str, count: int = 10) -> list[JSON]:
        data = await self._get(
            GEOCODING_URL,
            {"name": name.strip(), "count": count, "language": "en", "format": "json"},
        )
        results: list[JSON] = data.get("results") or []
        return results

    async def get_place(self, place_id: int) -> JSON | None:
        try:
            return await self._get(
                GEOCODING_GET_URL, {"id": place_id, "language": "en"}
            )
        except UpstreamError as exc:
            if isinstance(
                exc.__cause__, httpx.HTTPStatusError
            ) and exc.__cause__.response.status_code in (400, 404):
                return None
            raise

    async def forecast(self, latitude: float, longitude: float) -> JSON:
        """One call returns everything the UIs need for a place.

        Current conditions, 48 hourly points and 16 daily points: views slice
        this locally, so changing 3/7/16 days hits the cache, not the API.
        """
        return await self._get(
            FORECAST_URL,
            {
                "latitude": round(latitude, 4),
                "longitude": round(longitude, 4),
                "current": CURRENT_FIELDS,
                "hourly": HOURLY_FIELDS,
                "daily": DAILY_FIELDS,
                "forecast_days": MAX_FORECAST_DAYS,
                "forecast_hours": HOURLY_HOURS,
                "timezone": "auto",
            },
        )


def _error_reason(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and body.get("reason"):
        return str(body["reason"])
    return response.text[:200]
