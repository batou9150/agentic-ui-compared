import httpx
import pytest
import respx
from weather_core import OpenMeteoClient, UpstreamError
from weather_core.client import FORECAST_URL, GEOCODING_GET_URL, GEOCODING_URL


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@respx.mock
async def test_cache_hits_until_ttl_expires() -> None:
    route = respx.get(GEOCODING_URL).mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    clock = FakeClock()
    client = OpenMeteoClient(cache_ttl=60, clock=clock)
    await client.search("Paris")
    await client.search("Paris")
    assert route.call_count == 1
    clock.now = 61
    await client.search("Paris")
    assert route.call_count == 2
    assert client.requests_sent == 2
    await client.aclose()


@respx.mock
async def test_http_error_carries_reason() -> None:
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(
            400, json={"error": True, "reason": "Latitude out of range"}
        )
    )
    client = OpenMeteoClient()
    with pytest.raises(UpstreamError, match="400: Latitude out of range"):
        await client.forecast(999, 0)
    await client.aclose()


@respx.mock
async def test_server_error_with_text_body() -> None:
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(502, text="Bad gateway"))
    client = OpenMeteoClient()
    with pytest.raises(UpstreamError, match="502: Bad gateway"):
        await client.forecast(1, 2)
    await client.aclose()


@respx.mock
async def test_timeout_becomes_upstream_error() -> None:
    respx.get(GEOCODING_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    client = OpenMeteoClient()
    with pytest.raises(UpstreamError, match="unavailable"):
        await client.search("Paris")
    await client.aclose()


@respx.mock
async def test_invalid_json_becomes_upstream_error() -> None:
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, text="not json"))
    client = OpenMeteoClient()
    with pytest.raises(UpstreamError):
        await client.search("Paris")
    await client.aclose()


@respx.mock
async def test_errors_are_not_cached() -> None:
    route = respx.get(GEOCODING_URL)
    route.side_effect = [httpx.Response(500, text="boom"), httpx.Response(200, json={})]
    client = OpenMeteoClient()
    with pytest.raises(UpstreamError):
        await client.search("Paris")
    assert await client.search("Paris") == []
    await client.aclose()


@respx.mock
async def test_get_place_server_error_propagates() -> None:
    respx.get(GEOCODING_GET_URL).mock(return_value=httpx.Response(503, text="down"))
    client = OpenMeteoClient()
    with pytest.raises(UpstreamError):
        await client.get_place(42)
    await client.aclose()
