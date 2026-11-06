"""The weather component catalog: the A2UI basic catalog plus Chart and Clock.

A surface declares exactly one catalogId, so the custom catalog is a superset
of the basic one. The client registers the same two components (see
a2ui/client/src/catalog.ts); this file is the agent-side schema used for the
LLM prompt and for validation.
"""

import copy
from collections.abc import Iterable
from functools import cache
from typing import Any, Literal

from a2ui.builder.v0_9 import ComponentBuilderNode
from a2ui.catalog_transformers.pruning import ComponentPruningTransformer
from a2ui.core import CatalogApi
from a2ui.core.basic_catalog import BasicCatalog
from a2ui.processor import CatalogConfig, InMemoryCatalogProvider
from a2ui.utils.renderer_state import validate_payload

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
    schema: dict[str, Any] = copy.deepcopy(BasicCatalog(A2UI_VERSION).to_json())
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


@cache
def weather_catalog() -> CatalogApi:
    """The full catalog: what the client renders, used to validate surfaces."""
    return InMemoryCatalogProvider(
        weather_catalog_schema(),
        protocol_version=A2UI_VERSION,
        catalog_id=WEATHER_CATALOG_ID,
    ).load()


def catalog_config(components: Iterable[str] | None = None) -> CatalogConfig:
    """The catalog given to the model, optionally pruned to some components."""
    transformers = (
        [ComponentPruningTransformer(list(components))] if components else None
    )
    return CatalogConfig(catalog=weather_catalog(), transformers=transformers)


def validate(messages: list[dict[str, Any]]) -> None:
    """Raise if a renderer holding the weather catalog would reject the messages."""
    validate_payload([weather_catalog()], messages)


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
