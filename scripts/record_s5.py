"""Record what the A2UI agent composes for S5 in a Live run (Gemini).

Needs the Live A2UI agent running (`make a2ui-agent` or `make compare`) and
Gemini credentials in .env. Writes scenarios/recorded/S5-a2ui-compose.json,
which Scripted mode replays (validated against the catalog on replay).

Usage: uv run python scripts/record_s5.py [--agent http://localhost:10002]
"""

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from a2ui_agent.catalog import weather_catalog

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scenarios" / "recorded" / "S5-a2ui-compose.json"
PROMPT = "Compare Paris and Tokyo over the next 7 days on one chart"
DESIGNED = ("weather-", "forecast-", "picker-", "clock-")  # surfaces built by tools
EXTENSION = "https://a2ui.org/a2a-extension/a2ui/v0.9.1"


def is_composed(message: dict[str, Any]) -> bool:
    """True for surfaces the model wrote itself (not built by a tool)."""
    body = next(v for k, v in message.items() if k != "version")
    return not str(body.get("surfaceId", "")).startswith(DESIGNED)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent",
        default=f"http://localhost:{os.environ.get('A2UI_AGENT_PORT', '10002')}",
    )
    args = parser.parse_args()
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
