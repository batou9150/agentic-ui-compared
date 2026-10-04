ENV_FILE := $(if $(wildcard .env),--env-file .env,)

.PHONY: install test lint typecheck fixtures mcp-apps mcp-apps-views a2ui a2ui-agent a2ui-client compare compare-scripted e2e measure

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
	uv run mypy core/src mcp-apps/server/src a2ui/agent/src
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

# ---- A2UI ------------------------------------------------------------------

# A2A agent on http://localhost:$${A2UI_AGENT_PORT:-10002} (Live mode needs Gemini credentials).
a2ui-agent:
	uv run $(ENV_FILE) a2ui-agent

# Standalone web client on http://localhost:5174 (talks to the agent above).
a2ui-client:
	npm run dev -w a2ui/client

# Both, in parallel.
a2ui:
	$(MAKE) -j2 a2ui-agent a2ui-client

# ---- Comparison harness ----------------------------------------------------

# Both backends twice (Scripted: fixtures, Live: real API) + UI on :8080.
compare: mcp-apps-views
	./scripts/compare.sh

# Scripted backends only (no network, no LLM): what the e2e tests drive.
compare-scripted: mcp-apps-views
	COMPARE_SCRIPTED_ONLY=1 ./scripts/compare.sh

# Playwright e2e on both panes, Scripted mode (starts compare-scripted itself).
e2e:
	npm run e2e -w scenarios

# ---- Measurements ----------------------------------------------------------

# Median of N Scripted runs per scenario + code and artifact sizes.
# Writes measurements/summary.json, docs/measurements.md, COMPARISON.md block.
# Live token/LLM numbers: make measure ARGS="--mode live --runs 3" (uses Gemini).
measure:
	uv run python scripts/measure.py $(ARGS)
