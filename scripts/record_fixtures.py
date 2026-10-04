"""Record the Open-Meteo responses used by tests and Scripted mode.

Run sparingly (a few dozen requests): uv run python scripts/record_fixtures.py
It goes through the real WeatherService, so the recorded requests are exactly
the ones the app sends.
"""

import asyncio
import json

import httpx
from weather_core import OpenMeteoClient, Place, WeatherService
from weather_core.fixtures import FIXTURES_DIR, fixture_path

CITIES = ["Paris", "Lyon", "Tokyo", "New York", "Springfield"]
NOT_FOUND = "Zzzqqx"


class RecordingTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await super().handle_async_request(request)
        await response.aread()
        path = fixture_path(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(response.json(), indent=1, ensure_ascii=False) + "\n"
        )
        print(f"recorded {path.relative_to(FIXTURES_DIR)} ({response.status_code})")
        return response


async def main() -> None:
    service = WeatherService(
        OpenMeteoClient(transport=RecordingTransport(), cache_ttl=3600)
    )
    for city in CITIES:
        resolution = await service.resolve(city)
        places: list[Place] = list(resolution.candidates)
        if resolution.place is not None:
            places.append(resolution.place)
        for place in places:
            await service.client.forecast(place.latitude, place.longitude)
            await service.client.get_place(place.id)
    await service.client.search(NOT_FOUND)
    await service.client.get_place(1)
    await service.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
