"""Validate A2UI messages against the official 1.0 JSON schemas.

The protocol schemas come from a2ui-agent-sdk (`a2ui.utils.schemas`).
agent_to_renderer.json references `catalog.json`, which is mapped to our
weather catalog (a superset of the basic catalog). The catalog's own
`common_types.json` references resolve against its $id, so the common types
are registered there too.
"""

import json
from functools import cache
from typing import Any

from a2ui.utils.schemas import load_agent_to_renderer_schema, load_common_types_schema
from a2ui_agent.catalog import A2UI_VERSION, WEATHER_CATALOG_ID, weather_catalog_schema
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

BASE = "https://a2ui.org/specification/v1_0/"
CATALOG_BASE = WEATHER_CATALOG_ID.rsplit("/", 1)[0] + "/"


@cache
def message_validator() -> Draft202012Validator:
    a2r = load_agent_to_renderer_schema(A2UI_VERSION)
    common = Resource.from_contents(load_common_types_schema(A2UI_VERSION))
    registry = Registry().with_resources(
        [
            (BASE + "agent_to_renderer.json", Resource.from_contents(a2r)),
            (BASE + "common_types.json", common),
            (CATALOG_BASE + "common_types.json", common),
            (BASE + "catalog.json", Resource.from_contents(weather_catalog_schema())),
        ]
    )
    return Draft202012Validator(a2r, registry=registry)


def assert_spec_valid(messages: list[dict[str, Any]]) -> None:
    validator = message_validator()
    for m in messages:
        errors = sorted(validator.iter_errors(m), key=lambda e: list(e.path))
        assert not errors, f"{json.dumps(m)[:300]}\n" + "\n".join(
            e.message for e in errors[:5]
        )
