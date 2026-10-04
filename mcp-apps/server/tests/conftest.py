from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mcp import Client
from mcp_apps_server import build_server
from mcp_apps_server.server import VIEW_FILES
from weather_core import FixtureTransport, OpenMeteoClient, WeatherService

FROZEN_NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def views_dir(tmp_path: Path) -> Path:
    for name in VIEW_FILES.values():
        (tmp_path / name).write_text(f"<!doctype html><title>{name}</title>")
    return tmp_path


@pytest.fixture
def connect(views_dir: Path) -> Callable[[], AbstractAsyncContextManager[Client]]:
    """Open the in-process client inside the test task (anyio cancel scopes
    must be entered and exited in the same task, which fixtures do not do)."""

    @asynccontextmanager
    async def _connect() -> AsyncIterator[Client]:
        service = WeatherService(
            OpenMeteoClient(transport=FixtureTransport()), clock=lambda: FROZEN_NOW
        )
        async with Client(build_server(service, views_dir)) as c:
            yield c

    return _connect


Connect = Callable[[], AbstractAsyncContextManager[Client]]
