"""Run the A2UI agent over A2A (JSON-RPC): `uv run a2ui-agent`.

Env: A2UI_AGENT_PORT (default 10002), AGENT_MODEL, Gemini credentials (Live
mode only), OPEN_METEO_MODE.
"""

import logging
import os

import uvicorn

from .server import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("A2UI_AGENT_PORT", "10002"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
