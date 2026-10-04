"""Recorded Open-Meteo responses, served through an httpx transport.

Used by tests and by Scripted mode (OPEN_METEO_MODE=fixtures) so both
backends run offline and deterministically on identical data.

Layout under `weather_core/fixtures/`:
    geocoding/search_<name>.json   (lower-case, spaces as '-')
    geocoding/get_<id>.json
    forecast/<lat>_<lon>.json      (coordinates as sent, rounded to 4 decimals)

Record or refresh them with `uv run python scripts/record_fixtures.py`.
"""

import json
from pathlib import Path

import httpx

from .client import FORECAST_URL, GEOCODING_GET_URL, GEOCODING_URL

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def fixture_path(request: httpx.Request) -> Path:
    url = str(request.url.copy_with(query=None))
    params = request.url.params
    if url == GEOCODING_URL:
        return FIXTURES_DIR / "geocoding" / f"search_{slug(params['name'])}.json"
    if url == GEOCODING_GET_URL:
        return FIXTURES_DIR / "geocoding" / f"get_{int(params['id'])}.json"
    if url == FORECAST_URL:
        lat, lon = float(params["latitude"]), float(params["longitude"])
        return FIXTURES_DIR / "forecast" / f"{lat:.4f}_{lon:.4f}.json"
    raise ValueError(f"No fixture mapping for {url}")


def slug(name: str) -> str:
    return "-".join(name.strip().casefold().split())


class FixtureTransport(httpx.AsyncBaseTransport):
    """Answers from recorded JSON; unknown requests get a 404 with a clear reason."""

    def __init__(self, directory: Path = FIXTURES_DIR) -> None:
        self.directory = directory
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        try:
            path = self.directory / fixture_path(request).relative_to(FIXTURES_DIR)
        except ValueError as exc:
            return httpx.Response(404, json={"error": True, "reason": str(exc)})
        if not path.exists():
            reason = f"No recorded fixture {path.relative_to(self.directory)}"
            return httpx.Response(404, json={"error": True, "reason": reason})
        payload = json.loads(path.read_text())
        status = 400 if isinstance(payload, dict) and payload.get("error") else 200
        return httpx.Response(status, json=payload)
