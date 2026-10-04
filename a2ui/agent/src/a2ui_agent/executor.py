"""A2A executor: routes each request to one of three paths.

- user action (A2UI `action` DataPart): handled deterministically, no LLM,
  like an MCP App view calling a tool directly;
- scripted step (message metadata `scripted: {tool, args}`): the tool runs
  without an LLM, then its designed surface is rendered (Scripted mode);
- free text: the ADK agent (Gemini) runs; designed surfaces are streamed as
  soon as a tool returns, and a layout composed by the model is validated
  (one retry on error).

What a user action changes is noted and handed to the model on the next turn,
the equivalent of MCP Apps' `ui/update-model-context`.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCard, DataPart, Message, Part, TaskState, TextPart
from a2a.utils import new_agent_parts_message, new_task
from a2ui.a2a.extension import try_activate_a2ui_extension
from a2ui.a2a.parts import create_a2ui_part
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from weather_core import (
    CityWeather,
    Forecast,
    Resolution,
    Units,
    WeatherError,
    WeatherService,
)

from . import surfaces
from .agent import a2ui_format, build_agent
from .catalog import A2UI_VERSION, weather_catalog
from .tools import UI_SINK, UiRequest, make_tools

logger = logging.getLogger(__name__)

APP_NAME = "weather_a2ui"
USER_ID = "user"
MAX_COMPOSE_RETRIES = 1


class WeatherAgentExecutor(AgentExecutor):
    def __init__(
        self,
        service: WeatherService,
        agent_card: AgentCard,
        agent_factory: Callable[[], LlmAgent] | None = None,
    ) -> None:
        self.service = service
        self.card = agent_card
        self.tools = make_tools(service)
        self._agent_factory = agent_factory or (lambda: build_agent(self.tools))
        self._runner: Runner | None = None
        self._sessions = InMemorySessionService()
        self._surface_counts: dict[str, int] = defaultdict(int)
        self._ui_notes: dict[str, list[str]] = defaultdict(list)

    # ---- A2A entry point ----------------------------------------------------

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        assert message is not None
        task = context.current_task or new_task(message)
        if context.current_task is None:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        a2ui_active = try_activate_a2ui_extension(context, self.card) is not None
        conv = task.context_id

        def reply(parts: list[Part], metadata: dict[str, Any] | None = None) -> Message:
            if not a2ui_active:  # graceful degradation: text only
                parts = [p for p in parts if not isinstance(p.root, DataPart)]
            msg = new_agent_parts_message(parts, task.context_id, task.id)
            msg.metadata = metadata
            return msg

        metadata: dict[str, Any] = {"path": "live"}
        try:
            action = _find_action(message)
            scripted = (message.metadata or {}).get("scripted")
            if action is not None:
                metadata["path"] = "action"
                parts = await self.on_action(conv, action)
            elif scripted:
                metadata["path"] = "scripted"
                parts = await self.on_scripted(conv, scripted)
            else:

                async def stream(parts: list[Part]) -> None:
                    await updater.update_status(TaskState.working, reply(parts))

                parts, usage = await self.on_live(
                    conv, context.get_user_input(), stream
                )
                metadata["usage"] = usage
        except WeatherError as exc:
            parts = [Part(root=TextPart(text=str(exc)))]
        await updater.update_status(
            TaskState.completed, reply(parts, metadata), final=True
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancellation is not supported in this demo.")

    # ---- rendering designed surfaces ---------------------------------------

    def _surface_id(self, conv: str, kind: str) -> str:
        self._surface_counts[conv] += 1
        return f"{kind}-{self._surface_counts[conv]}"

    def render(self, conv: str, req: UiRequest) -> list[surfaces.Message]:
        result, units = req.result, Units(req.args.get("units", "metric"))
        if isinstance(result, Resolution):
            then = "forecast" if req.tool == "get_forecast" else "weather"
            sid = self._surface_id(conv, "picker")
            return surfaces.picker_surface(
                sid, result, then=then, units=units, days=int(req.args.get("days", 7))
            )
        if isinstance(result, CityWeather):
            return surfaces.weather_surface(self._surface_id(conv, "weather"), result)
        if isinstance(result, Forecast):
            return surfaces.forecast_surface(self._surface_id(conv, "forecast"), result)
        if isinstance(result, list):
            return surfaces.world_clock_surface(self._surface_id(conv, "clock"), result)
        raise TypeError(f"No designed surface for {type(result).__name__}")

    # ---- user actions (no LLM) -----------------------------------------------

    async def on_action(self, conv: str, action: dict[str, Any]) -> list[Part]:
        name = action.get("name")
        ctx = action.get("context") or {}
        sid = action["surfaceId"]
        place_id = int(ctx["placeId"])
        units = Units(ctx.get("units", "metric"))
        days = int(ctx.get("days", 7))
        if name == "pick_place" and ctx.get("then") == "forecast":
            f = await self.service.forecast(place_id=place_id, days=days, units=units)
            assert isinstance(f, Forecast)
            msgs = [
                surfaces.update_components(sid, surfaces.forecast_layout()),
                surfaces.update_data(sid, surfaces.forecast_data(f)),
            ]
            note = f"The user picked {f.place.label}. {f.summary}"
        elif name == "pick_place":
            w = await self.service.city_weather(place_id=place_id, units=units)
            assert isinstance(w, CityWeather)
            msgs = surfaces.weather_surface(sid, w, create=False)
            note = f"The user picked {w.place.label}. {w.summary}"
        elif name == "set_forecast":
            f = await self.service.forecast(place_id=place_id, days=days, units=units)
            assert isinstance(f, Forecast)
            msgs = surfaces.forecast_update(sid, f)
            note = f"The user changed the forecast view. {f.summary}"
        else:
            return [Part(root=TextPart(text=f"Unknown action {name!r}."))]
        self._ui_notes[conv].append(note)
        return _a2ui_parts(msgs)

    # ---- scripted steps (no LLM) ---------------------------------------------

    async def on_scripted(self, conv: str, step: dict[str, Any]) -> list[Part]:
        if "compose" in step:  # replay a layout recorded from a Live run
            recorded = step["compose"]
            try:
                weather_catalog().validate(recorded["messages"])
            except Exception as exc:
                return [
                    Part(root=TextPart(text=f"The recorded layout is invalid: {exc}"))
                ]
            text = (
                [Part(root=TextPart(text=recorded["text"]))]
                if recorded.get("text")
                else []
            )
            return [*_a2ui_parts(recorded["messages"]), *text]
        tool = self.tools.get(step.get("tool", ""))
        if tool is None:
            return [Part(root=TextPart(text=f"Unknown tool {step.get('tool')!r}."))]
        sink: list[UiRequest] = []
        token = UI_SINK.set(sink)
        try:
            result = await tool(**(step.get("args") or {}))
        finally:
            UI_SINK.reset(token)
        text = result.get("summary") or result.get("error_message", "")
        msgs = [m for req in sink for m in self.render(conv, req)]
        return [*_a2ui_parts(msgs), Part(root=TextPart(text=text))]

    # ---- live (LLM) ----------------------------------------------------------

    def runner(self) -> Runner:
        if self._runner is None:
            self._runner = Runner(
                app_name=APP_NAME,
                agent=self._agent_factory(),
                session_service=self._sessions,
            )
        return self._runner

    async def on_live(
        self,
        conv: str,
        text: str,
        stream: Callable[[list[Part]], Any],
    ) -> tuple[list[Part], dict[str, int]]:
        session = await self._sessions.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=conv
        )
        if session is None:
            await self._sessions.create_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=conv
            )
        notes = self._ui_notes.pop(conv, [])
        prompt = "\n".join([*(f"[UI context] {n}" for n in notes), text])
        usage = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0}

        final_text = await self._run_turn(conv, prompt, stream, usage)
        parts, errors = self._parse_composed(final_text)
        retries = 0
        while errors and retries < MAX_COMPOSE_RETRIES:
            retries += 1
            fix = (
                "The A2UI JSON you produced is invalid: "
                + "; ".join(errors)
                + ". Reply again with the complete corrected A2UI JSON."
            )
            final_text = await self._run_turn(conv, fix, stream, usage)
            parts, errors = self._parse_composed(final_text)
        if errors:
            parts.append(
                Part(
                    root=TextPart(
                        text="(The generated layout was invalid and was not shown.)"
                    )
                )
            )
        usage["compose_retries"] = retries
        return parts, usage

    async def _run_turn(
        self,
        conv: str,
        prompt: str,
        stream: Callable[[list[Part]], Any],
        usage: dict[str, int],
    ) -> str:
        sink: list[UiRequest] = []
        token = UI_SINK.set(sink)
        texts: list[str] = []
        try:
            async for event in self.runner().run_async(
                user_id=USER_ID,
                session_id=conv,
                new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
            ):
                if event.usage_metadata is not None and not event.partial:
                    usage["llm_calls"] += 1
                    usage["input_tokens"] += (
                        event.usage_metadata.prompt_token_count or 0
                    )
                    usage["output_tokens"] += (
                        event.usage_metadata.candidates_token_count or 0
                    )
                if sink:  # a tool returned: render its designed surface now
                    msgs = [m for req in sink for m in self.render(conv, req)]
                    sink.clear()
                    await stream(_a2ui_parts(msgs))
                if event.is_final_response() and event.content and event.content.parts:
                    texts += [p.text for p in event.content.parts if p.text]
        finally:
            UI_SINK.reset(token)
        return "\n".join(texts)

    def _parse_composed(self, text: str) -> tuple[list[Part], list[str]]:
        """Split the model's reply into text and (validated) composed A2UI."""
        parser = a2ui_format().parser
        if not parser.has_format_content(text, complete=True):
            return [Part(root=TextPart(text=text))] if text.strip() else [], []
        parts: list[Part] = []
        errors: list[str] = []
        try:
            response_parts = parser.parse_response(text)
        except Exception as exc:  # malformed JSON or schema error from the parser
            return [], [str(exc)]
        for rp in response_parts:
            if rp.text and rp.text.strip():
                parts.append(Part(root=TextPart(text=rp.text)))
            if rp.a2ui_json:
                msgs = (
                    rp.a2ui_json if isinstance(rp.a2ui_json, list) else [rp.a2ui_json]
                )
                try:
                    weather_catalog().validate(msgs)
                except Exception as exc:
                    errors.append(str(exc))
                    continue
                parts += _a2ui_parts(msgs)
        return parts, errors


def _a2ui_parts(messages: list[dict[str, Any]]) -> list[Part]:
    return [create_a2ui_part(m, version=A2UI_VERSION) for m in messages]


def _find_action(message: Message) -> dict[str, Any] | None:
    for part in message.parts:
        if isinstance(part.root, DataPart):
            data = part.root.data
            if isinstance(data, dict) and isinstance(data.get("action"), dict):
                action: dict[str, Any] = data["action"]
                return action
    return None


__all__ = ["WeatherAgentExecutor"]
