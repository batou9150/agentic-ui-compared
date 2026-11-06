"""The ADK agent used in Live mode (Gemini), over A2A or AG-UI.

The two transports share the role, the tools and the catalog schema. They
differ only in how a composed layout leaves the agent (A2UI JSON in the reply
over A2A, the compose_ui tool over AG-UI, whose middleware reads tool results)
and in how a click arrives (handled without the model over A2A, a message the
model answers over AG-UI).
"""

import os
from functools import cache

from a2ui.inference_formats.direct_json.format import DirectJsonFormat
from a2ui.inference_formats.direct_json.parser import DirectJsonParser
from a2ui.inference_formats.direct_json.schema_prompt import schema_to_prompt
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, Gemini
from google.genai import types

from .catalog import WEATHER_CATALOG_ID, catalog_config, weather_catalog
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

TOOLS = """You are a concise assistant for weather, forecasts and local time in cities.

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
"""

COMPOSE = f"""- If the request needs a layout no tool provides (for example several cities on
  ONE chart, or a side-by-side comparison), call the tools with show_ui=false to
  get the data, then compose a new surface yourself as A2UI JSON (version
  "v0.9.1", catalogId "{WEATHER_CATALOG_ID}", a new unique surfaceId). Use the
  Chart component for series over days. Put literal values in the components or
  in an updateDataModel message. Always end the layout with a caption Text
  "{ATTRIBUTION_TEXT}".
"""

ROLE = TOOLS + COMPOSE

AGUI_RULES = """- Show a composed layout by calling compose_ui with the JSON array of A2UI
  messages as a2ui_json; never write A2UI JSON in your reply. If compose_ui
  returns an error, fix the layout and call it again.
- A message starting with "[UI action]" reports a click on a surface you showed.
  Answer it with the matching tool call, passing the place_id, days and units
  from its context and surface_id set to that surface, so the surface is redrawn
  in place: "pick_place" calls get_forecast if its context says then=forecast,
  get_weather otherwise; "set_forecast" calls get_forecast. Then reply with at
  most one short sentence.
"""

AGUI_ROLE = TOOLS + COMPOSE + AGUI_RULES


@cache
def a2ui_format() -> DirectJsonFormat:
    """The format the model writes in: only the components it may compose with."""
    pruned = catalog_config(COMPOSE_COMPONENTS).transformed_catalog
    return DirectJsonFormat(catalogs=[pruned], allowed_messages=COMPOSE_MESSAGES)


@cache
def a2ui_parser() -> DirectJsonParser:
    """Reads composed layouts and checks them against the full weather catalog."""
    return DirectJsonFormat(catalogs=[weather_catalog()]).create_parser()


def instruction() -> str:
    return f"{ROLE}\n\n{a2ui_format().prompt_generator.generate()}"


def agui_instruction() -> str:
    """Same role and catalog schema, without the SDK's "reply with <a2ui-json>"
    workflow rules, which would contradict compose_ui."""
    fmt = a2ui_format()
    schema = schema_to_prompt(fmt.catalogs, allowed_messages=COMPOSE_MESSAGES)
    return f"{AGUI_ROLE}\n\n{schema}"


def model_name() -> str:
    return os.environ.get("AGENT_MODEL", DEFAULT_MODEL)


def build_agent(
    tools: dict[str, Tool], model: BaseLlm | None = None, text: str | None = None
) -> LlmAgent:
    text = text if text is not None else instruction()
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
