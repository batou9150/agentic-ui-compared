"""WMO weather interpretation codes (Open-Meteo `weather_code`).

Labels come from the Open-Meteo documentation. Icon keys are a small, stable
vocabulary that both UIs map to their own artwork:
clear, partly-cloudy, overcast, fog, drizzle, rain, freezing-rain, snow,
showers, snow-showers, thunderstorm, unknown. `clear` and `partly-cloudy`
get a `-night` suffix when it is dark.
"""

from .models import Condition

_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "clear"),
    1: ("Mainly clear", "clear"),
    2: ("Partly cloudy", "partly-cloudy"),
    3: ("Overcast", "overcast"),
    45: ("Fog", "fog"),
    48: ("Depositing rime fog", "fog"),
    51: ("Light drizzle", "drizzle"),
    53: ("Moderate drizzle", "drizzle"),
    55: ("Dense drizzle", "drizzle"),
    56: ("Light freezing drizzle", "freezing-rain"),
    57: ("Dense freezing drizzle", "freezing-rain"),
    61: ("Slight rain", "rain"),
    63: ("Moderate rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Light freezing rain", "freezing-rain"),
    67: ("Heavy freezing rain", "freezing-rain"),
    71: ("Slight snowfall", "snow"),
    73: ("Moderate snowfall", "snow"),
    75: ("Heavy snowfall", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Slight rain showers", "showers"),
    81: ("Moderate rain showers", "showers"),
    82: ("Violent rain showers", "showers"),
    85: ("Slight snow showers", "snow-showers"),
    86: ("Heavy snow showers", "snow-showers"),
    95: ("Thunderstorm", "thunderstorm"),
    96: ("Thunderstorm with slight hail", "thunderstorm"),
    99: ("Thunderstorm with heavy hail", "thunderstorm"),
}

_NIGHT_VARIANTS = {"clear", "partly-cloudy"}


def condition(code: int, *, is_day: bool = True) -> Condition:
    """Map a WMO code to a Condition; unknown codes do not raise."""
    label, icon = _CODES.get(code, ("Unknown conditions", "unknown"))
    if not is_day and icon in _NIGHT_VARIANTS:
        icon = f"{icon}-night"
    return Condition(code=code, label=label, icon=icon)


ICON_KEYS: frozenset[str] = frozenset(
    {icon for _, icon in _CODES.values()}
    | {f"{icon}-night" for icon in _NIGHT_VARIANTS}
    | {"unknown"}
)
