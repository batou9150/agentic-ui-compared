#!/usr/bin/env bash
# `make compare`: both implementations twice (Scripted on fixtures, Live on the
# real API) plus the comparison UI. Ctrl+C stops everything.
# Kept compatible with the bash 3.2 that ships with macOS.
set -eo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=""
[ -f .env ] && ENV_FILE="--env-file .env"

pids=""
cleanup() { [ -n "$pids" ] && kill $pids 2>/dev/null || true; }
trap cleanup EXIT INT TERM
start() { "$@" & pids="$pids $!"; }

FIXED="OPEN_METEO_MODE=fixtures WEATHER_FIXED_NOW=2026-10-04T12:00:00Z"
start env $FIXED MCP_APPS_PORT="${SCRIPTED_MCP_APPS_PORT:-3101}" uv run $ENV_FILE mcp-apps-server
start env $FIXED A2UI_AGENT_PORT="${SCRIPTED_A2UI_AGENT_PORT:-10102}" uv run $ENV_FILE a2ui-agent
start env OPEN_METEO_MODE=live uv run $ENV_FILE mcp-apps-server
start env OPEN_METEO_MODE=live uv run $ENV_FILE a2ui-agent
start npm run dev -w compare

echo "Comparison UI: http://localhost:${COMPARE_PORT:-8080}"
wait
