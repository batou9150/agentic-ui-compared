"""Record what the A2UI agent composes for S5 in a Live run (Gemini).

Needs the Live A2UI agent running (`make a2ui-agent` or `make compare`) and
Gemini credentials in .env. Writes scenarios/recorded/S5-a2ui-compose.json,
which Scripted mode replays (validated against the catalog on replay).

Usage: uv run python scripts/record_s5.py [--agent http://localhost:10002]

--rebind (offline) keeps the recorded layout and replaces the numbers in its
chart with the Scripted fixtures, so the S5 replay shows the same data as the
MCP Apps side. Only the series values and day labels change, never the layout.
"""

import argparse
import asyncio
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from a2ui_agent.catalog import weather_catalog
from weather_core import FixtureTransport, Forecast, OpenMeteoClient, WeatherService

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scenarios" / "recorded" / "S5-a2ui-compose.json"
PROMPT = "Compare Paris and Tokyo over the next 7 days on one chart"
DESIGNED = ("weather-", "forecast-", "picker-", "clock-")  # surfaces built by tools
EXTENSION = "https://a2ui.org/a2a-extension/a2ui/v0.9.1"
SCRIPTED_NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)  # WEATHER_FIXED_NOW in compare.sh
SERIES = re.compile(r"^(?P<city>.+?) \((?P<kind>Max|Min)\b")  # e.g. "Paris (Max)"


def is_composed(message: dict[str, Any]) -> bool:
    """True for surfaces the model wrote itself (not built by a tool)."""
    body = next(v for k, v in message.items() if k != "version")
    return not str(body.get("surfaceId", "")).startswith(DESIGNED)


async def fixture_forecasts(cities: set[str]) -> dict[str, Forecast]:
    service = WeatherService(
        OpenMeteoClient(transport=FixtureTransport()), clock=lambda: SCRIPTED_NOW
    )
    out = {}
    for city in cities:
        f = await service.forecast(city, None, 7)
        assert isinstance(f, Forecast)
        out[city] = f
    return out


def rebind() -> None:
    doc = json.loads(OUT.read_text())
    if "rebound" in doc:
        raise SystemExit(f"{OUT.relative_to(ROOT)} is already rebound.")
    charts = [
        c
        for m in doc["messages"]
        for c in m.get("updateComponents", {}).get("components", [])
        if c.get("component") == "Chart"
    ]
    matches = [(s, SERIES.match(s["label"])) for c in charts for s in c["series"]]
    unknown = [s["label"] for s, m in matches if m is None]
    if not charts or unknown:
        raise SystemExit(f"Cannot map the chart series to cities: {unknown}")
    forecasts = asyncio.run(fixture_forecasts({m["city"] for _, m in matches if m}))
    for chart in charts:
        # One label row for the chart, from the first city, as the model did.
        first = SERIES.match(chart["series"][0]["label"])
        assert first
        chart["labels"] = [f"{d.date:%a %-d}" for d in forecasts[first["city"]].daily]
    for series, m in matches:
        assert m
        field = "temperature_max" if m["kind"] == "Max" else "temperature_min"
        series["values"] = [getattr(d, field) for d in forecasts[m["city"]].daily]
    weather_catalog().validate(doc["messages"])
    doc["rebound"] = (
        "Series values and day labels replaced with the Scripted fixtures "
        f"(now = {SCRIPTED_NOW:%Y-%m-%dT%H:%MZ}) by scripts/record_s5.py --rebind; "
        "the layout is unchanged from the Live run."
    )
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"rebound {OUT.relative_to(ROOT)}: {len(matches)} series")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent",
        default=f"http://localhost:{os.environ.get('A2UI_AGENT_PORT', '10002')}",
    )
    parser.add_argument(
        "--rebind", action="store_true", help="offline: swap in fixture numbers"
    )
    args = parser.parse_args()
    if args.rebind:
        return rebind()
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "text", "text": PROMPT}],
            }
        },
    }
    response = httpx.post(
        args.agent, json=body, headers={"X-A2A-Extensions": EXTENSION}, timeout=180
    )
    response.raise_for_status()
    task: dict[str, Any] = response.json()["result"]
    final = task["status"]["message"]
    messages = [
        p["data"]
        for p in final["parts"]
        if p["kind"] == "data" and is_composed(p["data"])
    ]
    text = " ".join(p["text"] for p in final["parts"] if p["kind"] == "text").strip()
    usage = (final.get("metadata") or {}).get("usage", {})
    if not messages:
        raise SystemExit(
            f"The model did not compose a layout. It answered: {text!r} (usage {usage})"
        )
    weather_catalog().validate(messages)
    doc = {
        "source": f"Recorded from a Live run on {datetime.now(UTC):%Y-%m-%d} with "
        f"{os.environ.get('AGENT_MODEL', 'gemini-3.8-flash')} (usage {usage}).",
        "text": text,
        "messages": messages,
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(messages)} messages, retries {usage.get('compose_retries')}"
    )


if __name__ == "__main__":
    main()
