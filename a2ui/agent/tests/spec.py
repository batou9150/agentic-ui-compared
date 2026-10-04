"""Validate A2UI messages against the official v0.9.1 JSON schemas.

The schema files ship with a2ui-agent-sdk (a2ui/assets/0.9.1). Their $ids say
v0_9, and server_to_client.json references `catalog.json`, which is mapped to
our weather catalog (a superset of the basic catalog).
"""

import json
from functools import cache
from importlib import resources
from typing import Any

from a2ui_agent.catalog import weather_catalog_schema
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

BASE = "https://a2ui.org/specification/v0_9/"


def _load(name: str) -> dict[str, Any]:
    path = resources.files("a2ui.assets") / "0.9.1" / name
    data: dict[str, Any] = json.loads(path.read_text())
    return data


@cache
def message_validator() -> Draft202012Validator:
    s2c = _load("server_to_client.json")
    registry = Registry().with_resources(
        [
            (BASE + "server_to_client.json", Resource.from_contents(s2c)),
            (
                BASE + "common_types.json",
                Resource.from_contents(_load("common_types.json")),
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
