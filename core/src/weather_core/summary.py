"""Short text summaries derived from the models, for the LLM and for text-only hosts."""

from .models import (
    CurrentConditions,
    DailyPoint,
    HourlyPoint,
    LocalTime,
    Place,
    UnitLabels,
)


def current(
    place: Place, cur: CurrentConditions, local: LocalTime, u: UnitLabels
) -> str:
    return (
        f"{place.label}: {cur.condition.label.lower()}, {cur.temperature:g} {u.temperature} "
        f"(feels like {cur.feels_like:g} {u.temperature}), humidity {cur.humidity}%, "
        f"wind {cur.wind_speed:g} {u.wind_speed}. "
        f"Local time {local.iso:%H:%M} {local.abbreviation}."
    )


def forecast(place: Place, points: list[DailyPoint], u: UnitLabels) -> str:
    lines = [f"{len(points)}-day forecast for {place.label}:"]
    for p in points:
        lines.append(
            f"- {p.date:%a %Y-%m-%d}: {p.condition.label.lower()}, "
            f"{p.temperature_min:g} to {p.temperature_max:g} {u.temperature}, "
            f"{p.precipitation_sum:g} {u.precipitation} precipitation"
            + (
                f" ({p.precipitation_probability}% chance)"
                if p.precipitation_probability is not None
                else ""
            )
            + "."
        )
    return "\n".join(lines)


def hourly(place: Place, points: list[HourlyPoint], u: UnitLabels) -> str:
    if not points:
        return f"No hourly data for {place.label}."
    temps = [p.temperature for p in points]
    return (
        f"Next {len(points)} hours in {place.label}: "
        f"{min(temps):g} to {max(temps):g} {u.temperature}, "
        f"starting {points[0].condition.label.lower()}."
    )


def ambiguous(query: str, candidates: list[Place]) -> str:
    options = "; ".join(f"{c.label} (id {c.id})" for c in candidates)
    return f"'{query}' matches several places, ask the user to choose: {options}."
