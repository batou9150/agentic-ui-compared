"""The ADK agent used in Live mode (Gemini). Scripted mode never builds it."""

import os
from functools import cache

from a2ui.inference_formats.direct_json.format import DirectJsonFormat
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, Gemini
from google.genai import types

from .catalog import A2UI_VERSION, WEATHER_CATALOG_ID, catalog_config
from .surfaces import ATTRIBUTION_TEXT
from .tools import Tool

DEFAULT_MODEL = "gemini-3.8-flash"

# Components the model may use when it composes a layout itself (S5).
COMPOSE_COMPONENTS = ["Text", "Row", "Column", "Card", "Divider", "Chart", "Clock"]
COMPOSE_MESSAGES = [
    "CreateSurfaceMessage",
    "UpdateComponentsMessage",
    "UpdateDataModelMessage",
]

ROLE = f"""You are a concise assistant for weather, forecasts and local time in cities.

Tools:
- get_weather: current conditions + local time for ONE city (renders a weather card).
- get_forecast: daily forecast for ONE city (renders a chart with day/unit controls).
- get_world_clock: time + weather for SEVERAL cities (renders a grid of live clocks).
- get_hourly: hourly data for one city (data only).
Never guess weather data: always call a tool.

UI rules:
- By default tools render their own designed UI (show_ui=true). After such a call,
  answer with ONE short sentence; do not repeat the numbers, the user sees them.
- If a city is ambiguous, the tool shows a picker; tell the user to pick one.
- If the request needs a layout no tool provides (for example several cities on
  ONE chart, or a side-by-side comparison), call the tools with show_ui=false to
  get the data, then compose a new surface yourself as A2UI JSON (version
  "v0.9.1", catalogId "{WEATHER_CATALOG_ID}", a new unique surfaceId). Use the
  Chart component for series over days. Put literal values in the components or
  in an updateDataModel message. Always end the layout with a caption Text
  "{ATTRIBUTION_TEXT}".
"""


@cache
def a2ui_format() -> DirectJsonFormat:
    return DirectJsonFormat(version=A2UI_VERSION, catalogs=[catalog_config()])


def instruction() -> str:
    return a2ui_format().prompt_generator.generate(
        role_description=ROLE,
        include_schema=True,
        allowed_components=COMPOSE_COMPONENTS,
        allowed_messages=COMPOSE_MESSAGES,
    )


def model_name() -> str:
    return os.environ.get("AGENT_MODEL", DEFAULT_MODEL)


def build_agent(tools: dict[str, Tool], model: BaseLlm | None = None) -> LlmAgent:
    text = instruction()
    llm = model or Gemini(
        model=model_name(), retry_options=types.HttpRetryOptions(attempts=3)
    )
    return LlmAgent(
        name="weather_a2ui_agent",
        model=llm,
        description="Weather, forecast and local time, answered with A2UI surfaces.",
        # A provider, not a string: ADK would treat the JSON schema's braces as
        # session-state placeholders.
        instruction=lambda _ctx: text,
        tools=list(tools.values()),
    )
