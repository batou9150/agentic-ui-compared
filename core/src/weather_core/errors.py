"""Typed errors. Both implementations turn these into protocol-level errors."""


class WeatherError(Exception):
    """Base class for every error raised by weather_core."""

    code = "weather_error"


class InvalidRequestError(WeatherError):
    """The caller asked for something Open-Meteo cannot answer (e.g. 20 days)."""

    code = "invalid_request"


class PlaceNotFoundError(WeatherError):
    """Geocoding returned no match for the query."""

    code = "place_not_found"

    def __init__(self, query: str) -> None:
        super().__init__(f"No location found for '{query}'.")
        self.query = query


class UpstreamError(WeatherError):
    """Open-Meteo is unreachable, timed out or answered with an error."""

    code = "upstream_error"
