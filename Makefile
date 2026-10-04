ENV_FILE := $(if $(wildcard .env),--env-file .env,)

.PHONY: install test lint typecheck fixtures mcp-apps mcp-apps-views

install:
	uv sync
	npm install

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	npm run lint

typecheck:
	uv run mypy core/src mcp-apps/server/src
	npm run typecheck

# Re-record Open-Meteo fixtures (a few dozen live requests, run sparingly).
fixtures:
	uv run python scripts/record_fixtures.py

# ---- MCP Apps --------------------------------------------------------------

mcp-apps-views:
	npm run build -w mcp-apps/views

# MCP server on http://localhost:$${MCP_APPS_PORT:-3001}/mcp (Streamable HTTP).
mcp-apps: mcp-apps-views
	uv run $(ENV_FILE) mcp-apps-server
