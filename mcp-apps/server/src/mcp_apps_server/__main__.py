"""Run the server over Streamable HTTP: `uv run mcp-apps-server`.

Env: MCP_APPS_PORT (default 3001), MCP_APPS_PUBLIC_HOST (a tunnel host name,
e.g. abc.trycloudflare.com, to test in claude.ai / Claude Desktop).
"""

import os

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware

from .server import build_server

LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOCAL_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def create_app() -> Starlette:
    public_host = os.environ.get("MCP_APPS_PUBLIC_HOST", "").strip()
    hosts, origins = list(LOCAL_HOSTS), list(LOCAL_ORIGINS)
    if public_host:
        hosts.append(public_host)
        origins.append(f"https://{public_host}")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )
    app = build_server().streamable_http_app(transport_security=security)
    # The compare harness runs in the browser on another port: allow CORS from
    # localhost and expose the session headers the MCP client needs.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id", "mcp-protocol-version"],
    )
    return app


def main() -> None:
    port = int(os.environ.get("MCP_APPS_PORT", "3001"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
