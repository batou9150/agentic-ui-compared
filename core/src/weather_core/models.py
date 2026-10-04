"""Typed domain models shared by both UI implementations.

Every tool in mcp-apps/ and a2ui/ returns these models (serialised with
`model_dump(mode="json")`), so both UIs render exactly the same data.
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Units(StrEnum):
    METRIC = "metric"  # °C, km/h, mm
    IMPERIAL = "imperial"  # °F, mph, inch


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class Place(_Model):
    """A geocoded location, as returned by Open-Meteo geocoding."""

    id: int
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    country_code: str | None = None
    region: str | None = Field(default=None, description="First-level admin area")
    timezone: str
    population: int | None = None

    @property
    def label(self) -> str:
        """Human label used in text summaries and pickers: 'Paris, France'."""
        parts = [self.name, self.region, self.country]
        seen: list[str] = []
        for part in parts:
            if part and part not in seen:
                seen.append(part)
        return ", ".join(seen)


class Condition(_Model):
    """A WMO weather code with its label and an icon key the UIs map to art."""

    code: int
    label: str
    icon: str


class UnitLabels(_Model):
    temperature: str
    wind_speed: str
    precipitation: str


class CurrentConditions(_Model):
    observed_at: datetime = Field(description="Local time of the observation")
    temperature: float
    feels_like: float
    humidity: int = Field(description="Relative humidity, %")
    wind_speed: float
    wind_direction: int = Field(description="Degrees, meteorological")
    is_day: bool
    condition: Condition


class DailyPoint(_Model):
    date: date
    condition: Condition
    temperature_min: float
    temperature_max: float
    precipitation_sum: float
    precipitation_probability: int | None = None
    sunrise: datetime | None = None
    sunset: datetime | None = None


class HourlyPoint(_Model):
    time: datetime
    temperature: float
    precipitation_probability: int | None = None
    condition: Condition


class LocalTime(_Model):
    timezone: str
    abbreviation: str
    utc_offset_seconds: int
    iso: datetime = Field(description="Current local time, timezone-aware")


class CityWeather(_Model):
    """S1 / S4 payload: a place, its current conditions and its local time."""

    place: Place
    units: Units
    unit_labels: UnitLabels
    current: CurrentConditions
    local_time: LocalTime
    summary: str


class Forecast(_Model):
    """S3 payload: a daily series for 1 to 16 days."""

    place: Place
    units: Units
    unit_labels: UnitLabels
    days: int
    daily: list[DailyPoint]
    summary: str


class HourlyForecast(_Model):
    place: Place
    units: Units
    unit_labels: UnitLabels
    hourly: list[HourlyPoint]
    summary: str


class Resolution(_Model):
    """Outcome of resolving a free-text city name (S2).

    Exactly one of `place` (unambiguous) or `candidates` (user must pick) is
    meaningful: `ambiguous` tells which.
    """

    query: str
    ambiguous: bool
    place: Place | None = None
    candidates: list[Place] = Field(default_factory=list)
    summary: str


class Attribution(_Model):
    text: str = "Weather data by Open-Meteo.com"
    url: str = "https://open-meteo.com/"
    license: str = "CC BY 4.0"


ATTRIBUTION = Attribution()
