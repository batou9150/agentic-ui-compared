"""The HTTP app: CORS for the browser harness and DNS-rebinding protection."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp_apps_server.__main__ import create_app
from starlette.testclient import TestClient


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch, views_dir: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("MCP_APPS_VIEWS_DIR", str(views_dir))
    monkeypatch.setenv("OPEN_METEO_MODE", "fixtures")
    monkeypatch.delenv("MCP_APPS_PUBLIC_HOST", raising=False)
    with TestClient(create_app(), base_url="http://localhost:3001") as client:
        yield client


def test_cors_preflight_from_harness(http: TestClient) -> None:
    r = http.options(
        "/mcp",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,mcp-session-id",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_foreign_host_is_rejected(http: TestClient) -> None:
    r = http.post("/mcp", headers={"Host": "evil.example"}, json={})
    assert r.status_code in (403, 421)
