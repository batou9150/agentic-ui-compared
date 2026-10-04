"""The domain operations both implementations call. All business rules live here.

- resolving a free-text city, including the ambiguity rule (S2)
- current conditions + local time for a place (S1, S4)
- daily forecast for 1 to 16 days, in metric or imperial (S3)
- hourly series (available to the LLM for off-script requests, S5)

Callers pass either a city name or a place id (the id a picker sends back).
When a name is ambiguous, operations return a `Resolution` with candidates
instead of guessing; the UI shows a picker and calls again with `place_id`.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from . import summary
from .client import HOURLY_HOURS, MAX_FORECAST_DAYS, OpenMeteoClient
from .errors import InvalidRequestError, PlaceNotFoundError
from .models import (
    CityWeather,
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
from .wmo import condition

MAX_CANDIDATES = 5
MAX_CITIES = 8
# A name is ambiguous when the runner-up has at least this share of the top
# match's population: Springfield MO/MA/IL are ambiguous, Paris FR/TX is not.
AMBIGUITY_RATIO = 0.1

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class WeatherService:
    def __init__(self, client: OpenMeteoClient, *, clock: Clock = _utc_now) -> None:
        self.client = client
        self._clock = clock
        self._places: dict[int, Place] = {}

    # ---- places -----------------------------------------------------------

    async def search(self, query: str, count: int = MAX_CANDIDATES) -> list[Place]:
        """Matches for `query`, exact-name matches first, most populated first."""
        if not query.strip():
            raise InvalidRequestError("The city name is empty.")
        raw = await self.client.search(query, count=10)
        places = [self._remember(_place(r)) for r in raw]
        wanted = query.strip().casefold()
        exact = [p for p in places if p.name.casefold() == wanted]
        others = [p for p in places if p.name.casefold() != wanted]
        exact.sort(key=lambda p: p.population or 0, reverse=True)
        return (exact + others)[:count]

    async def resolve(self, query: str) -> Resolution:
        places = await self.search(query, count=10)
        if not places:
            raise PlaceNotFoundError(query)
        wanted = query.strip().casefold()
        exact = [p for p in places if p.name.casefold() == wanted]
        if _is_ambiguous(exact):
            candidates = exact[:MAX_CANDIDATES]
            return Resolution(
                query=query,
                ambiguous=True,
                candidates=candidates,
                summary=summary.ambiguous(query, candidates),
            )
        place = exact[0] if exact else places[0]
        return Resolution(
            query=query,
            ambiguous=False,
            place=place,
            summary=f"Resolved to {place.label}.",
        )

    async def get_place(self, place_id: int) -> Place:
        if place_id in self._places:
            return self._places[place_id]
        raw = await self.client.get_place(place_id)
        if raw is None:
            raise PlaceNotFoundError(f"id {place_id}")
        return self._remember(_place(raw))

    async def place_or_resolution(
        self, city: str | None = None, place_id: int | None = None
    ) -> Place | Resolution:
        """The place to use, or a Resolution the UI must turn into a picker."""
        if place_id is not None:
            return await self.get_place(place_id)
        if city is None:
            raise InvalidRequestError("Give a city name or a place id.")
        resolution = await self.resolve(city)
        if resolution.ambiguous or resolution.place is None:
            return resolution
        return resolution.place

    def _remember(self, place: Place) -> Place:
        self._places[place.id] = place
        return place

    # ---- weather ----------------------------------------------------------

    async def city_weather(
        self,
        city: str | None = None,
        place_id: int | None = None,
        units: Units = Units.METRIC,
    ) -> CityWeather | Resolution:
        target = await self.place_or_resolution(city, place_id)
        if isinstance(target, Resolution):
            return target
        return await self.city_weather_for(target, units)

    async def city_weather_for(
        self, place: Place, units: Units = Units.METRIC
    ) -> CityWeather:
        data = await self.client.forecast(place.latitude, place.longitude)
        cur = data["current"]
        is_day = bool(cur["is_day"])
        current = CurrentConditions(
            observed_at=datetime.fromisoformat(cur["time"]),
            temperature=_temp(cur["temperature_2m"], units),
            feels_like=_temp(cur["apparent_temperature"], units),
            humidity=int(cur["relative_humidity_2m"]),
            wind_speed=_speed(cur["wind_speed_10m"], units),
            wind_direction=int(cur["wind_direction_10m"]),
            is_day=is_day,
            condition=condition(int(cur["weather_code"]), is_day=is_day),
        )
        local = self.local_time(place)
        labels = unit_labels(units)
        return CityWeather(
            place=place,
            units=units,
            unit_labels=labels,
            current=current,
            local_time=local,
            summary=summary.current(place, current, local, labels),
        )

    async def many_city_weather(
        self,
        cities: list[str] | None = None,
        place_ids: list[int] | None = None,
        units: Units = Units.METRIC,
    ) -> list[CityWeather | Resolution]:
        """World clock (S4): one entry per requested city, in request order.

        Ambiguous names come back as a Resolution so the UI can ask which one.
        """
        queries: list[tuple[str | None, int | None]] = [(c, None) for c in cities or []]
        queries += [(None, i) for i in place_ids or []]
        if not queries:
            raise InvalidRequestError("Give at least one city.")
        if len(queries) > MAX_CITIES:
            raise InvalidRequestError(f"At most {MAX_CITIES} cities at once.")
        return list(
            await asyncio.gather(*(self.city_weather(c, i, units) for c, i in queries))
        )

    async def forecast(
        self,
        city: str | None = None,
        place_id: int | None = None,
        days: int = 7,
        units: Units = Units.METRIC,
    ) -> Forecast | Resolution:
        if not 1 <= days <= MAX_FORECAST_DAYS:
            raise InvalidRequestError(
                f"Can only forecast between 1 and {MAX_FORECAST_DAYS} days, not {days}."
            )
        target = await self.place_or_resolution(city, place_id)
        if isinstance(target, Resolution):
            return target
        data = await self.client.forecast(target.latitude, target.longitude)
        d = data["daily"]
        points = [
            DailyPoint(
                date=datetime.fromisoformat(day).date(),
                condition=condition(int(d["weather_code"][i])),
                temperature_min=_temp(d["temperature_2m_min"][i], units),
                temperature_max=_temp(d["temperature_2m_max"][i], units),
                precipitation_sum=_precip(d["precipitation_sum"][i], units),
                precipitation_probability=_opt_int(
                    d["precipitation_probability_max"][i]
                ),
                sunrise=_opt_dt(d["sunrise"][i]),
                sunset=_opt_dt(d["sunset"][i]),
            )
            for i, day in enumerate(d["time"][:days])
        ]
        labels = unit_labels(units)
        return Forecast(
            place=target,
            units=units,
            unit_labels=labels,
            days=days,
            daily=points,
            summary=summary.forecast(target, points, labels),
        )

    async def hourly(
        self,
        city: str | None = None,
        place_id: int | None = None,
        hours: int = 24,
        units: Units = Units.METRIC,
    ) -> HourlyForecast | Resolution:
        if not 1 <= hours <= HOURLY_HOURS:
            raise InvalidRequestError(
                f"Can only give between 1 and {HOURLY_HOURS} hours, not {hours}."
            )
        target = await self.place_or_resolution(city, place_id)
        if isinstance(target, Resolution):
            return target
        data = await self.client.forecast(target.latitude, target.longitude)
        h = data["hourly"]
        points = [
            HourlyPoint(
                time=datetime.fromisoformat(t),
                temperature=_temp(h["temperature_2m"][i], units),
                precipitation_probability=_opt_int(h["precipitation_probability"][i]),
                condition=condition(int(h["weather_code"][i])),
            )
            for i, t in enumerate(h["time"][:hours])
        ]
        labels = unit_labels(units)
        return HourlyForecast(
            place=target,
            units=units,
            unit_labels=labels,
            hourly=points,
            summary=summary.hourly(target, points, labels),
        )

    def local_time(self, place: Place) -> LocalTime:
        zone = ZoneInfo(place.timezone)
        now = self._clock().astimezone(zone)
        offset = now.utcoffset()
        return LocalTime(
            timezone=place.timezone,
            abbreviation=now.tzname() or place.timezone,
            utc_offset_seconds=int(offset.total_seconds()) if offset else 0,
            iso=now,
        )


# ---- helpers ---------------------------------------------------------------


def _is_ambiguous(exact: list[Place]) -> bool:
    if len(exact) < 2:
        return False
    top = exact[0].population or 0
    runner_up = exact[1].population or 0
    if top == 0:
        return True  # no population data: let the user choose
    return runner_up >= top * AMBIGUITY_RATIO


def _place(raw: dict[str, Any]) -> Place:
    return Place(
        id=int(raw["id"]),
        name=raw["name"],
        latitude=float(raw["latitude"]),
        longitude=float(raw["longitude"]),
        country=raw.get("country"),
        country_code=raw.get("country_code"),
        region=raw.get("admin1"),
        timezone=raw.get("timezone") or "UTC",
        population=raw.get("population"),
    )


def unit_labels(units: Units) -> UnitLabels:
    if units is Units.IMPERIAL:
        return UnitLabels(temperature="°F", wind_speed="mph", precipitation="in")
    return UnitLabels(temperature="°C", wind_speed="km/h", precipitation="mm")


def _temp(celsius: float, units: Units) -> float:
    if units is Units.IMPERIAL:
        return round(celsius * 9 / 5 + 32, 1)
    return round(float(celsius), 1)


def _speed(kmh: float, units: Units) -> float:
    if units is Units.IMPERIAL:
        return round(kmh / 1.609344, 1)
    return round(float(kmh), 1)


def _precip(mm: float | None, units: Units) -> float:
    value = float(mm or 0.0)
    if units is Units.IMPERIAL:
        return round(value / 25.4, 2)
    return round(value, 1)


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _opt_dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)
