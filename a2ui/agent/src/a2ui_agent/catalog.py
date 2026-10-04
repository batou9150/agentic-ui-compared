"""The weather component catalog: the A2UI basic catalog plus Chart and Clock.

A surface declares exactly one catalogId, so the custom catalog is a superset
of the basic one. The client registers the same two components (see
a2ui/client/src/catalog.ts); this file is the agent-side schema used for the
LLM prompt and for validation.
"""

import copy
import json
from functools import cache
from importlib import resources
from typing import Any, Literal

from a2ui.builder.v0_9 import ComponentBuilderNode
from a2ui.schema.catalog import A2uiCatalog, CatalogConfig
from a2ui.schema.catalog_provider import A2uiCatalogProvider

A2UI_VERSION = "0.9.1"
MESSAGE_VERSION = "v0.9.1"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
WEATHER_CATALOG_ID = (
    "https://github.com/batou9150/agentic-ui-compared/a2ui/weather-catalog.json"
)

COMMON = "https://a2ui.org/specification/v0_9/common_types.json#/$defs"


def _component(
    name: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "allOf": [
            {"$ref": f"{COMMON}/ComponentCommon"},
            {"$ref": "#/$defs/CatalogComponentCommon"},
            {
                "type": "object",
                "properties": {"component": {"const": name}, **properties},
                "required": ["component", *required],
            },
        ],
        "unevaluatedProperties": False,
    }


CHART = _component(
    "Chart",
    {
        "title": {
            "$ref": f"{COMMON}/DynamicString",
            "description": "Optional chart title.",
        },
        "labels": {
            "$ref": f"{COMMON}/DynamicStringList",
            "description": "X axis labels, one per data point (e.g. day names).",
        },
        "series": {
            "$ref": f"{COMMON}/DynamicValue",
            "description": (
                "Array of series objects {label: string, kind: 'line'|'bar', "
                "axis: 'left'|'right', values: number[]}, literal or bound to a "
                "data model path. Lines and bars can be mixed; use the right axis "
                "for a second unit such as precipitation."
            ),
        },
        "leftUnit": {
            "$ref": f"{COMMON}/DynamicString",
            "description": "Left axis unit.",
        },
        "rightUnit": {
            "$ref": f"{COMMON}/DynamicString",
            "description": "Right axis unit.",
        },
    },
    ["labels", "series"],
)

CLOCK = _component(
    "Clock",
    {
        "timeZone": {
            "$ref": f"{COMMON}/DynamicString",
            "description": "IANA time zone, e.g. 'Asia/Tokyo'. The clock ticks on the client.",
        },
        "showSeconds": {"type": "boolean", "default": True},
    },
    ["timeZone"],
)


@cache
def weather_catalog_schema() -> dict[str, Any]:
    basic_path = resources.files("a2ui.assets") / A2UI_VERSION / "catalog.json"
    schema: dict[str, Any] = copy.deepcopy(json.loads(basic_path.read_text()))
    schema["$id"] = WEATHER_CATALOG_ID
    schema["catalogId"] = WEATHER_CATALOG_ID
    schema["title"] = "Weather catalog (A2UI basic + Chart + Clock)"
    schema["components"]["Chart"] = CHART
    schema["components"]["Clock"] = CLOCK
    any_component = schema["$defs"]["anyComponent"]
    any_component["oneOf"] += [
        {"$ref": "#/components/Chart"},
        {"$ref": "#/components/Clock"},
    ]
    return schema


class _WeatherCatalogProvider(A2uiCatalogProvider):
    def load(self) -> dict[str, Any]:
        return copy.deepcopy(weather_catalog_schema())


def catalog_config() -> CatalogConfig:
    return CatalogConfig(name="weather", provider=_WeatherCatalogProvider())


@cache
def weather_catalog() -> A2uiCatalog:
    return A2uiCatalog.from_config(catalog_config(), version=A2UI_VERSION)


# ---- builder nodes for the two custom components ---------------------------


class Chart(ComponentBuilderNode):
    component: Literal["Chart"] = "Chart"
    title: Any = None
    labels: Any
    series: Any
    leftUnit: Any = None
    rightUnit: Any = None


class Clock(ComponentBuilderNode):
    component: Literal["Clock"] = "Clock"
    timeZone: Any
    showSeconds: bool = True
