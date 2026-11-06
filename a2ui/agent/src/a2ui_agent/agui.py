"""AG-UI transport for the A2UI agent (ag_ui_adk), following the AG-UI conventions.

- Designed surfaces travel in tool results as an `a2ui_operations` envelope,
  which `@ag-ui/a2ui-middleware` (in the Node relay of the compare harness)
  turns into `a2ui-surface` activity events.
- A layout the model composes (S5) goes through the compose_ui tool, in the
  same envelope: the middleware does not read A2UI written in text replies.
- A click is a turn of the agent: the middleware sends it as a synthetic
  `log_a2ui_event` tool call and result, and the model answers it with a tool
  call. ag_ui_adk 0.12 drops that pair (it is never a pending ADK call), so
  `AguiRequestShim` rewrites it as a user message with the same text.

Scripted mode (`forwardedProps.scripted`) swaps Gemini for a replay model that
makes the tool call the scenario specifies, so a run goes through the same
agent loop, events and middleware with no LLM.
"""

import inspect
import json
import re
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any

from a2ui.parser.messages import to_message_dicts
from a2ui.parser.response_part import A2uiPart
from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from fastapi import FastAPI
from google.adk.models import BaseLlm, Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import PrivateAttr
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from weather_core import WeatherService

from .agent import a2ui_parser, agui_instruction, build_agent, model_name
from .rendering import SurfaceRenderer
from .tools import UI_SINK, Tool, UiRequest, make_tools

APP_NAME = "weather_a2ui_agui"
USER_ID = "user"
ACTION_TOOL = "log_a2ui_event"  # the middleware's synthetic tool for a click
ACTION_PREFIX = "[UI action] "
ACTION_TEXT = re.compile(
    r'User performed action "(?P<name>[^"]*)" on surface "(?P<surface>[^"]*)"'
    r".*?Context: (?P<context>\{.*\})",
    re.DOTALL,
)


@dataclass
class Usage:
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    compose_retries: int = 0


@dataclass
class Run:
    thread_id: str
    scripted: dict[str, Any] | None
    usage: Usage = field(default_factory=Usage)


RUN: ContextVar[Run | None] = ContextVar("AGUI_RUN", default=None)


# ---- the request shim -------------------------------------------------------


def clicks_as_user_turns(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace the middleware's synthetic click pair by a user message."""
    ids = {
        call.get("id")
        for m in messages
        if m.get("role") == "assistant"
        for call in m.get("toolCalls") or []
        if (call.get("function") or {}).get("name") == ACTION_TOOL
    }
    if not ids:
        return messages
    out: list[dict[str, Any]] = []
    for m in messages:
        calls = m.get("toolCalls") or []
        if (
            m.get("role") == "assistant"
            and calls
            and all(c.get("id") in ids for c in calls)
        ):
            continue
        if m.get("role") == "tool" and m.get("toolCallId") in ids:
            out.append(
                {
                    "id": m["id"],
                    "role": "user",
                    "content": ACTION_PREFIX + str(m["content"]),
                }
            )
            continue
        out.append(m)
    return out


class AguiRequestShim:
    """ASGI middleware in front of the ag_ui_adk endpoint.

    Rewrites clicks (see clicks_as_user_turns) and opens a `Run` for the
    request: its thread, its Scripted step if any, and its LLM usage, which
    the relay reads from GET /usage when the run ends.
    """

    def __init__(self, app: ASGIApp, runs: dict[str, Run]) -> None:
        self.app = app
        self.runs = runs

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        token = None
        if isinstance(data, dict):
            data["messages"] = clicks_as_user_turns(data.get("messages") or [])
            props = data.get("forwardedProps") or {}
            run = Run(str(data.get("threadId", "")), props.get("scripted"))
            self.runs[run.thread_id] = run
            token = RUN.set(run)
            body = json.dumps(data).encode()
            scope = {
                **scope,
                "headers": [
                    (k, v) for k, v in scope["headers"] if k != b"content-length"
                ]
                + [(b"content-length", str(len(body)).encode())],
            }
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        try:
            await self.app(scope, replay, send)
        finally:
            if token is not None:
                RUN.reset(token)


# ---- tools ---------------------------------------------------------------------


SURFACE_ID_DOC = (
    "\n        surface_id: Id of a surface already shown, to redraw it in place"
    " after a UI action on it. Omit otherwise.\n"
)


def with_surfaces(name: str, tool: Tool, renderer: SurfaceRenderer) -> Tool:
    """The tool, with its designed surface added to the result as a2ui_operations."""
    sig = inspect.signature(tool)
    params = list(sig.parameters.values())
    if "show_ui" in sig.parameters:
        params.append(
            inspect.Parameter(
                "surface_id",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=str | None,
            )
        )
    params.append(
        inspect.Parameter(
            "tool_context", inspect.Parameter.KEYWORD_ONLY, annotation=ToolContext
        )
    )

    async def wrapper(**kwargs: Any) -> dict[str, Any]:
        context: ToolContext = kwargs.pop("tool_context")
        surface_id = kwargs.pop("surface_id", None)
        sink: list[UiRequest] = []
        token = UI_SINK.set(sink)
        try:
            result = await tool(**kwargs)
        finally:
            UI_SINK.reset(token)
        conv = context.session.id
        ops = [m for req in sink for m in renderer.render(conv, req, surface_id)]
        return {**result, "a2ui_operations": ops} if ops else result

    wrapper.__name__ = name
    doc = tool.__doc__ or ""
    wrapper.__doc__ = (
        doc.rstrip() + SURFACE_ID_DOC if "show_ui" in sig.parameters else doc
    )
    wrapper.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
    return wrapper


async def compose_ui(a2ui_json: str) -> dict[str, Any]:
    """Show a layout you composed for a request no tool's UI covers.

    Args:
        a2ui_json: JSON array of A2UI v0.9.1 messages (createSurface, then
            updateComponents and optionally updateDataModel) for ONE new surface.
    """
    try:
        parts = a2ui_parser().parse_response(
            a2ui_json, wrapped="<a2ui-json>" in a2ui_json
        )
    except Exception as exc:  # malformed JSON or a layout the client rejects
        run = RUN.get()
        if run is not None:
            run.usage.compose_retries += 1
        return {"status": "error", "error_message": f"Invalid layout: {exc}"}
    ops = [
        m for p in parts if isinstance(p, A2uiPart) for m in to_message_dicts(p.a2ui)
    ]
    if not ops:
        return {"status": "error", "error_message": "No A2UI messages found."}
    return {"status": "success", "ui_shown": True, "a2ui_operations": ops}


def agui_tools(service: WeatherService, renderer: SurfaceRenderer) -> dict[str, Tool]:
    tools = {
        name: with_surfaces(name, tool, renderer)
        for name, tool in make_tools(service).items()
    }
    tools["compose_ui"] = compose_ui
    return tools


# ---- the model: Gemini (Live) or replay (Scripted), with usage per run --------


# The replay model reports zero usage (and ADK logs no "missing usage" warning).
NO_USAGE = types.GenerateContentResponseUsageMetadata(
    prompt_token_count=0, candidates_token_count=0
)


def _text(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        usage_metadata=NO_USAGE,
    )


def _call(name: str, args: dict[str, Any]) -> LlmResponse:
    call = types.FunctionCall(name=name, args=args)
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(function_call=call)]),
        usage_metadata=NO_USAGE,
    )


def action_call(text: str) -> tuple[str, dict[str, Any]] | None:
    """The tool call a click asks for, as the role's UI action rule describes it."""
    match = ACTION_TEXT.search(text)
    if match is None:
        return None
    ctx = json.loads(match["context"])
    args: dict[str, Any] = {
        "place_id": int(ctx["placeId"]),
        "units": ctx.get("units", "metric"),
        "surface_id": match["surface"],
    }
    if match["name"] == "set_forecast" or ctx.get("then") == "forecast":
        return "get_forecast", {**args, "days": int(ctx.get("days", 7))}
    return "get_weather", args


def replay(request: LlmRequest, step: dict[str, Any]) -> LlmResponse:
    """What the scenario says the model does next (Scripted mode, no LLM)."""
    last = request.contents[-1] if request.contents else None
    parts = (last.parts or []) if last else []
    answered = next((p.function_response for p in parts if p.function_response), None)
    if answered is not None:  # after the tool call: the closing sentence
        result = answered.response or {}
        if "compose" in step:
            return _text(str(step["compose"].get("text", "")))
        if step.get("click"):
            return _text("")
        return _text(str(result.get("summary") or result.get("error_message", "")))
    if "compose" in step:
        messages = step["compose"]["messages"]
        return _call("compose_ui", {"a2ui_json": json.dumps(messages)})
    if "tool" in step:
        return _call(step["tool"], dict(step.get("args") or {}))
    said = " ".join(p.text or "" for p in parts)
    call = action_call(said)
    return _call(*call) if call else _text("")


class WeatherModel(BaseLlm):
    """Gemini in Live mode, the replay model in Scripted mode; counts usage."""

    model: str = "weather-agui"
    _live: BaseLlm | None = PrivateAttr(default=None)

    def live(self) -> BaseLlm:
        if self._live is None:
            self._live = Gemini(
                model=model_name(), retry_options=types.HttpRetryOptions(attempts=3)
            )
        return self._live

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        run = RUN.get()
        if run is not None and run.scripted is not None:
            yield replay(llm_request, run.scripted)
            return
        live = self.live()
        llm_request.model = live.model
        async for response in live.generate_content_async(llm_request, stream):
            if run is not None and response.usage_metadata and not response.partial:
                run.usage.llm_calls += 1
                run.usage.input_tokens += (
                    response.usage_metadata.prompt_token_count or 0
                )
                run.usage.output_tokens += (
                    response.usage_metadata.candidates_token_count or 0
                )
            yield response


# ---- the app ------------------------------------------------------------------


def create_agui_app(
    service: WeatherService, model_factory: Callable[[], BaseLlm] | None = None
) -> ASGIApp:
    renderer = SurfaceRenderer()
    model = (model_factory or WeatherModel)()
    agent = build_agent(agui_tools(service, renderer), model, agui_instruction())
    adk_agent = ADKAgent(
        adk_agent=agent,
        app_name=APP_NAME,
        user_id=USER_ID,
        use_in_memory_services=True,
    )
    runs: dict[str, Run] = {}
    app = FastAPI()

    @app.get("/usage")
    async def usage(threadId: str) -> dict[str, int]:
        run = runs.get(threadId)
        return asdict(run.usage) if run else asdict(Usage())

    add_adk_fastapi_endpoint(app, adk_agent, path="/")
    return AguiRequestShim(app, runs)


__all__ = ["action_call", "clicks_as_user_turns", "create_agui_app", "replay"]
