"""A2A server for the A2UI agent: agent card, request handler, CORS."""

import os

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2ui.a2a.extension import get_a2ui_agent_extension
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from weather_core import WeatherService, create_service

from .catalog import A2UI_VERSION, BASIC_CATALOG_ID, WEATHER_CATALOG_ID
from .executor import WeatherAgentExecutor


def agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="Weather (A2UI)",
        description="Weather, forecast and local time for cities, answered with A2UI surfaces.",
        url=base_url,
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text", "application/a2ui+json"],
        capabilities=AgentCapabilities(
            streaming=True,
            extensions=[
                get_a2ui_agent_extension(
                    A2UI_VERSION,
                    supported_catalog_ids=[WEATHER_CATALOG_ID, BASIC_CATALOG_ID],
                )
            ],
        ),
        skills=[
            AgentSkill(
                id="weather",
                name="Weather and local time",
                description="Current weather, daily forecast and local time for one or more cities.",
                tags=["weather", "time"],
                examples=["What's the weather in Paris?", "Forecast for Lyon"],
            )
        ],
    )


def create_app(
    service: WeatherService | None = None, executor: WeatherAgentExecutor | None = None
) -> Starlette:
    port = int(os.environ.get("A2UI_AGENT_PORT", "10002"))
    card = agent_card(os.environ.get("A2UI_PUBLIC_URL", f"http://localhost:{port}"))
    executor = executor or WeatherAgentExecutor(service or create_service(), card)
    handler = DefaultRequestHandler(
        agent_executor=executor, task_store=InMemoryTaskStore()
    )
    app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-A2A-Extensions"],
    )
    return app
