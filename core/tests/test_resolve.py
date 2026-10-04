import pytest
from weather_core import InvalidRequestError, PlaceNotFoundError, WeatherService


async def test_paris_is_not_ambiguous(service: WeatherService) -> None:
    r = await service.resolve("Paris")
    assert not r.ambiguous
    assert r.place is not None
    assert (r.place.country_code, r.place.timezone) == ("FR", "Europe/Paris")
    assert r.place.label == "Paris, Île-de-France Region, France"


async def test_springfield_is_ambiguous(service: WeatherService) -> None:
    r = await service.resolve("Springfield")
    assert r.ambiguous and r.place is None
    assert [c.region for c in r.candidates] == [
        "Missouri",
        "Massachusetts",
        "Illinois",
        "Ohio",
        "Tennessee",
    ]
    assert all(c.name == "Springfield" for c in r.candidates)
    assert "id 4409896" in r.summary


async def test_query_is_trimmed_and_case_insensitive(service: WeatherService) -> None:
    r = await service.resolve("  paris ")
    assert r.place is not None and r.place.country_code == "FR"


async def test_unknown_city(service: WeatherService) -> None:
    with pytest.raises(PlaceNotFoundError, match="Zzzqqx"):
        await service.resolve("Zzzqqx")


async def test_empty_query(service: WeatherService) -> None:
    with pytest.raises(InvalidRequestError):
        await service.resolve("   ")


async def test_get_place_uses_search_cache(service: WeatherService, transport) -> None:  # type: ignore[no-untyped-def]
    r = await service.resolve("Springfield")
    sent = len(transport.requests)
    place = await service.get_place(r.candidates[2].id)
    assert place.region == "Illinois"
    assert len(transport.requests) == sent


async def test_get_place_cold_and_unknown(service: WeatherService) -> None:
    place = await service.get_place(4409896)
    assert place.region == "Missouri"
    with pytest.raises(PlaceNotFoundError):
        await service.get_place(1)


async def test_place_or_resolution_needs_input(service: WeatherService) -> None:
    with pytest.raises(InvalidRequestError):
        await service.place_or_resolution()


async def test_search_keeps_non_exact_matches_last(service: WeatherService) -> None:
    places = await service.search("Springfield", count=10)
    names = [p.name for p in places]
    first_other = next(i for i, n in enumerate(names) if n != "Springfield")
    assert all(n != "Springfield" for n in names[first_other:])
