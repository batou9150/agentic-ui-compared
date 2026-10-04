"""Designed A2UI surfaces for the weather tools (the A2UI side's "views").

Each builder turns a weather_core model into A2UI v0.9.1 messages:
createSurface + updateComponents (layout, bound to data paths) +
updateDataModel (display values). Controls only need a data model update.
"""

from typing import Any

from a2ui.builder.v0_9 import Action, ActionEvent, DataBinding
from a2ui.builder.v0_9.catalogs.basic import Button, Card, Column, Row, Text
from weather_core import ATTRIBUTION, CityWeather, Forecast, Place, Resolution, Units

from .catalog import MESSAGE_VERSION, WEATHER_CATALOG_ID, Chart, Clock

Message = dict[str, Any]

ICONS = {
    "clear": "☀️",
    "clear-night": "🌙",
    "partly-cloudy": "⛅",
    "partly-cloudy-night": "☁️",
    "overcast": "☁️",
    "fog": "🌫️",
    "drizzle": "🌦️",
    "rain": "🌧️",
    "freezing-rain": "🧊",
    "snow": "❄️",
    "showers": "🌦️",
    "snow-showers": "🌨️",
    "thunderstorm": "⛈️",
    "unknown": "❔",
}

ATTRIBUTION_TEXT = f"{ATTRIBUTION.text} ({ATTRIBUTION.license})"
DAY_OPTIONS = (3, 7, 16)


def icon(key: str) -> str:
    return ICONS.get(key, ICONS["unknown"])


def _bind(path: str) -> DataBinding:
    return DataBinding(path=path)


def _msg(**body: Any) -> Message:
    return {"version": MESSAGE_VERSION, **body}


def create_surface(surface_id: str) -> Message:
    return _msg(
        createSurface={"surfaceId": surface_id, "catalogId": WEATHER_CATALOG_ID}
    )


def update_components(surface_id: str, root: Any) -> Message:
    return _msg(
        updateComponents={"surfaceId": surface_id, "components": root.flatten()}
    )


def update_data(surface_id: str, value: Any, path: str = "/") -> Message:
    return _msg(updateDataModel={"surfaceId": surface_id, "path": path, "value": value})


def _attribution() -> Text:
    return Text(text=ATTRIBUTION_TEXT, variant="caption")


# ---- S1 weather card --------------------------------------------------------


def weather_data(w: CityWeather) -> dict[str, Any]:
    u = w.unit_labels
    return {
        "place": w.place.label,
        "localTime": f"Local time {w.local_time.iso:%H:%M} {w.local_time.abbreviation}",
        "icon": icon(w.current.condition.icon),
        "temperature": f"{w.current.temperature:g}{u.temperature}",
        "condition": w.current.condition.label,
        "feelsLike": f"Feels like {w.current.feels_like:g}{u.temperature}",
        "humidity": f"Humidity {w.current.humidity}%",
        "wind": f"Wind {w.current.wind_speed:g} {u.wind_speed}",
    }


def weather_layout() -> Card:
    return Card(
        id="root",
        child=Column(
            children=[
                Text(text=_bind("/place"), variant="h2"),
                Text(text=_bind("/localTime"), variant="caption"),
                Row(
                    children=[
                        Text(text=_bind("/icon"), variant="h1"),
                        Text(text=_bind("/temperature"), variant="h1"),
                        Text(text=_bind("/condition")),
                    ],
                    align="center",
                ),
                Row(
                    children=[
                        Text(text=_bind("/feelsLike")),
                        Text(text=_bind("/humidity")),
                        Text(text=_bind("/wind")),
                    ],
                    justify="spaceBetween",
                ),
                _attribution(),
            ]
        ),
    )


def weather_surface(
    surface_id: str, w: CityWeather, *, create: bool = True
) -> list[Message]:
    head = [create_surface(surface_id)] if create else []
    return [
        *head,
        update_components(surface_id, weather_layout()),
        update_data(surface_id, weather_data(w)),
    ]


# ---- S2 place picker ---------------------------------------------------------


def picker_surface(
    surface_id: str,
    r: Resolution,
    *,
    then: str = "weather",
    units: Units = Units.METRIC,
    days: int = 7,
) -> list[Message]:
    """One Button per candidate (in the basic catalog only Button emits actions)."""

    def option(p: Place) -> Button:
        region = ", ".join(x for x in (p.region, p.country) if x)
        context = {"placeId": p.id, "then": then, "units": units.value, "days": days}
        return Button(
            child=Text(text=f"**{p.name}** {region}"),
            action=Action(event=ActionEvent(name="pick_place", context=context)),
        )

    layout = Card(
        id="root",
        child=Column(
            children=[
                Text(text=f"Which {r.query}?", variant="h2"),
                Text(text="Several places match. Pick one:", variant="caption"),
                Row(children=[option(p) for p in r.candidates]),
                _attribution(),
            ]
        ),
    )
    return [create_surface(surface_id), update_components(surface_id, layout)]


# ---- S3 forecast chart -------------------------------------------------------


def forecast_data(f: Forecast) -> dict[str, Any]:
    u = f.unit_labels
    unit_name = "°C" if f.units is Units.METRIC else "°F"
    return {
        "place": f.place.label,
        "placeId": f.place.id,
        "days": f.days,
        "units": f.units.value,
        "subtitle": f"{f.days}-day forecast · {unit_name}",
        "chart": {
            "labels": [f"{d.date:%a %-d}" for d in f.daily],
            "leftUnit": u.temperature,
            "rightUnit": u.precipitation,
            "series": [
                {
                    "label": f"Max {u.temperature}",
                    "kind": "line",
                    "axis": "left",
                    "values": [d.temperature_max for d in f.daily],
                },
                {
                    "label": f"Min {u.temperature}",
                    "kind": "line",
                    "axis": "left",
                    "values": [d.temperature_min for d in f.daily],
                },
                {
                    "label": f"Precipitation {u.precipitation}",
                    "kind": "bar",
                    "axis": "right",
                    "values": [d.precipitation_sum for d in f.daily],
                },
            ],
        },
    }


def _control(label: str, **context: Any) -> Button:
    # Unchanged settings are read from the data model when the button is clicked.
    full = {
        "placeId": _bind("/placeId"),
        "days": _bind("/days"),
        "units": _bind("/units"),
    }
    full.update(context)
    return Button(
        child=Text(text=label),
        variant="borderless",
        action=Action(event=ActionEvent(name="set_forecast", context=full)),
    )


def forecast_layout() -> Card:
    controls = [_control(f"{d} days", days=d) for d in DAY_OPTIONS] + [
        _control("°C", units=Units.METRIC.value),
        _control("°F", units=Units.IMPERIAL.value),
    ]
    return Card(
        id="root",
        child=Column(
            children=[
                Text(text=_bind("/place"), variant="h2"),
                Text(text=_bind("/subtitle"), variant="caption"),
                Row(children=controls),
                Chart(
                    labels=_bind("/chart/labels"),
                    series=_bind("/chart/series"),
                    leftUnit=_bind("/chart/leftUnit"),
                    rightUnit=_bind("/chart/rightUnit"),
                ),
                _attribution(),
            ]
        ),
    )


def forecast_surface(
    surface_id: str, f: Forecast, *, create: bool = True
) -> list[Message]:
    head = [create_surface(surface_id)] if create else []
    return [
        *head,
        update_components(surface_id, forecast_layout()),
        update_data(surface_id, forecast_data(f)),
    ]


def forecast_update(surface_id: str, f: Forecast) -> list[Message]:
    """A control click: same layout, new data only."""
    return [update_data(surface_id, forecast_data(f))]


# ---- S4 world clock ----------------------------------------------------------


def world_clock_surface(
    surface_id: str, items: list[CityWeather | Resolution]
) -> list[Message]:
    cards: list[Card] = []
    data: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        base = f"/cities/{i}"
        if isinstance(item, CityWeather):
            data.append(
                {
                    "name": item.place.name,
                    "subtitle": f"{item.place.country or ''} · {item.local_time.abbreviation}",
                    "timeZone": item.local_time.timezone,
                    "weather": f"{icon(item.current.condition.icon)} "
                    f"{item.current.temperature:g}{item.unit_labels.temperature} "
                    f"{item.current.condition.label}",
                }
            )
            cards.append(
                Card(
                    child=Column(
                        children=[
                            Text(text=_bind(f"{base}/name"), variant="h3"),
                            Text(text=_bind(f"{base}/subtitle"), variant="caption"),
                            Clock(timeZone=_bind(f"{base}/timeZone")),
                            Text(text=_bind(f"{base}/weather")),
                        ]
                    )
                )
            )
        else:
            regions = ", ".join(c.region or c.country or "" for c in item.candidates)
            data.append(
                {"name": item.query, "subtitle": f"Several places match: {regions}."}
            )
            cards.append(
                Card(
                    child=Column(
                        children=[
                            Text(text=_bind(f"{base}/name"), variant="h3"),
                            Text(text=_bind(f"{base}/subtitle"), variant="caption"),
                        ]
                    )
                )
            )
    layout = Column(id="root", children=[Row(children=cards), _attribution()])
    return [
        create_surface(surface_id),
        update_components(surface_id, layout),
        update_data(surface_id, {"cities": data}),
    ]
