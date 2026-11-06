"""Validate A2UI messages against the official v0.9.1 JSON schemas.

The protocol schemas come from a2ui-agent-sdk (`a2ui.utils.schemas`). Their
$ids say v0_9, and server_to_client.json references `catalog.json`, which is
mapped to our weather catalog (a superset of the basic catalog).
"""

import json
from functools import cache
from typing import Any

from a2ui.utils.schemas import load_agent_to_renderer_schema, load_common_types_schema
from a2ui_agent.catalog import A2UI_VERSION, weather_catalog_schema
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

BASE = "https://a2ui.org/specification/v0_9/"


@cache
def message_validator() -> Draft202012Validator:
    s2c = load_agent_to_renderer_schema(A2UI_VERSION)
    registry = Registry().with_resources(
        [
            (BASE + "server_to_client.json", Resource.from_contents(s2c)),
            (
                BASE + "common_types.json",
                Resource.from_contents(load_common_types_schema(A2UI_VERSION)),
            ),
            (BASE + "catalog.json", Resource.from_contents(weather_catalog_schema())),
        ]
    )
    return Draft202012Validator(s2c, registry=registry)


def assert_spec_valid(messages: list[dict[str, Any]]) -> None:
    validator = message_validator()
    for m in messages:
        errors = sorted(validator.iter_errors(m), key=lambda e: list(e.path))
        assert not errors, f"{json.dumps(m)[:300]}\n" + "\n".join(
            e.message for e in errors[:5]
        )
