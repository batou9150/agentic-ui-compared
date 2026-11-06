"""End to end over AG-UI (ag_ui_adk): Scripted replay, clicks as agent turns,
compose_ui, and Live with a fake LLM. The middleware (Node) is not involved:
these tests read the tool results it would turn into activity events, and send
clicks the way it rewrites them (a synthetic log_a2ui_event pair)."""

import contextlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from a2ui_agent.agui import (
    action_call,
    clicks_as_user_turns,
    create_agui_app,
)
from a2ui_agent.catalog import validate
from starlette.testclient import TestClient
from weather_core import WeatherService

from .fake_llm import FakeLlm, call, say
from .spec import assert_spec_valid

RECORDED = Path(__file__).parents[3] / "scenarios" / "recorded" / "S5-a2ui-compose.json"


class Thread:
    """A tiny AG-UI client: keeps the history, posts runs, parses SSE events."""

    def __init__(self, http: TestClient) -> None:
        # ag_ui_adk keeps sessions in a process-wide manager: one thread per test.
        self.http, self.thread_id, self.n = http, uuid.uuid4().hex, 0
        self.messages: list[dict[str, Any]] = []

    def run(self, forwarded: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.n += 1
        body = {
            "threadId": self.thread_id,
            "runId": f"r{self.n}",
            "state": {},
            "messages": self.messages,
            "tools": [],
            "context": [],
            "forwardedProps": forwarded or {},
        }
        r = self.http.post("/", json=body, headers={"accept": "text/event-stream"})
        assert r.status_code == 200, r.text
        events = [
            json.loads(line[5:])
            for line in r.text.splitlines()
            if line.startswith("data:")
        ]
        self._remember(events)
        return events

    def ask(
        self, text: str, scripted: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.messages.append({"id": f"u{self.n}", "role": "user", "content": text})
        return self.run({"scripted": scripted} if scripted is not None else None)

    def click(
        self, action: dict[str, Any], scripted: bool = True
    ) -> list[dict[str, Any]]:
        """What @ag-ui/a2ui-middleware does with forwardedProps.a2uiAction."""
        call_id = f"a{self.n}"
        text = (
            f'User performed action "{action["name"]}" on surface "{action["surfaceId"]}"'
            f" (component: {action.get('sourceComponentId', 'btn')})."
            f" Context: {json.dumps(action.get('context', {}))}"
        )
        self.messages += [
            {
                "id": f"aa{self.n}",
                "role": "assistant",
                "content": "",
                "toolCalls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "log_a2ui_event",
                            "arguments": json.dumps(action),
                        },
                    }
                ],
            },
            {
                "id": f"ar{self.n}",
                "role": "tool",
                "toolCallId": call_id,
                "content": text,
            },
        ]
        return self.run(
            {
                "a2uiAction": {"userAction": action},
                **({"scripted": {"click": True}} if scripted else {}),
            }
        )

    def _remember(self, events: list[dict[str, Any]]) -> None:
        text = "".join(
            e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT"
        )
        if text:
            self.messages.append(
                {"id": f"x{self.n}", "role": "assistant", "content": text}
            )

    def usage(self) -> dict[str, int]:
        data: dict[str, int] = self.http.get(
            "/usage", params={"threadId": self.thread_id}
        ).json()
        return data


def results(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        if e["type"] == "TOOL_CALL_RESULT":
            with contextlib.suppress(ValueError):  # a plain-text result
                out.append(json.loads(e["content"]))
    return out


def operations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [op for r in results(events) for op in r.get("a2ui_operations", [])]


def texts(events: list[dict[str, Any]]) -> str:
    return "".join(
        e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT"
    )


def kinds(ops: list[dict[str, Any]]) -> list[str]:
    return [next(k for k in op if k != "version") for op in ops]


def place_id(events: list[dict[str, Any]], label: str) -> int:
    """A candidate's id, as the ambiguous tool result lists it to the model."""
    summary = " ".join(str(r.get("summary", "")) for r in results(events))
    match = re.search(rf"{label}[^;()]*\(id (\d+)\)", summary)
    assert match, summary
    return int(match[1])


@pytest.fixture
def thread(service: WeatherService) -> Thread:
    return Thread(TestClient(create_agui_app(service)))


def test_scripted_tool_returns_designed_surface_in_tool_result(thread: Thread) -> None:
    events = thread.ask(
        "Weather in Paris", {"tool": "get_weather", "args": {"city": "Paris"}}
    )
    assert events[0]["type"] == "RUN_STARTED" and events[-1]["type"] == "RUN_FINISHED"
    ops = operations(events)
    assert kinds(ops) == ["createSurface", "updateComponents", "updateDataModel"]
    assert ops[0]["createSurface"]["surfaceId"] == "weather-1"
    assert_spec_valid(ops)
    validate(ops)
    assert "Paris" in texts(events)  # the replayed closing sentence is the summary
    assert thread.usage()["llm_calls"] == 0  # no LLM in Scripted mode


def test_scripted_click_is_an_agent_turn_that_redraws_the_picker(
    thread: Thread,
) -> None:
    first = thread.ask(
        "Weather in Springfield",
        {"tool": "get_weather", "args": {"city": "Springfield"}},
    )
    picker = operations(first)
    assert picker[0]["createSurface"]["surfaceId"] == "picker-1"
    pid = place_id(first, "Illinois")
    events = thread.click(
        {
            "name": "pick_place",
            "surfaceId": "picker-1",
            "context": {"placeId": pid, "then": "weather"},
        }
    )
    starts = [e["toolCallName"] for e in events if e["type"] == "TOOL_CALL_START"]
    assert starts == ["get_weather"]
    ops = operations(events)
    assert "createSurface" not in kinds(ops)  # redrawn in place
    assert {op[k]["surfaceId"] for op in ops for k in op if k != "version"} == {
        "picker-1"
    }
    assert "Illinois" in json.dumps(ops)
    assert texts(events) == ""  # the replay adds no sentence after a click


def test_scripted_forecast_controls_update_the_chart_in_place(thread: Thread) -> None:
    first = thread.ask(
        "Forecast for Lyon",
        {"tool": "get_forecast", "args": {"city": "Lyon", "days": 7}},
    )
    assert operations(first)[0]["createSurface"]["surfaceId"] == "forecast-1"
    data = next(
        op["updateDataModel"]["value"]
        for op in operations(first)
        if "updateDataModel" in op
    )
    pid = int(data["placeId"])
    ctx = {"placeId": pid, "days": 16, "units": "metric"}
    events = thread.click(
        {"name": "set_forecast", "surfaceId": "forecast-1", "context": ctx}
    )
    ops = operations(events)
    assert ops and all("createSurface" not in op for op in ops)
    assert "16-day" in json.dumps(ops)


def test_scripted_compose_goes_through_compose_ui(thread: Thread) -> None:
    recorded = json.loads(RECORDED.read_text())
    events = thread.ask("Compare Paris and Tokyo", {"compose": recorded})
    starts = [e["toolCallName"] for e in events if e["type"] == "TOOL_CALL_START"]
    assert starts == ["compose_ui"]
    ops = operations(events)
    assert ops == recorded["messages"]
    assert texts(events) == recorded["text"]


def test_invalid_compose_is_a_tool_error_and_counts_a_retry(thread: Thread) -> None:
    bad = {
        "messages": [{"version": "v0.9.1", "createSurface": {"surfaceId": "x"}}],
        "text": "t",
    }
    events = thread.ask("Compose", {"compose": bad})
    (result,) = results(events)
    assert result["status"] == "error" and "a2ui_operations" not in result
    assert thread.usage()["compose_retries"] == 1


def test_live_turn_with_fake_llm_counts_usage(service: WeatherService) -> None:
    llm = FakeLlm(turns=[call("get_weather", city="Paris"), say("Here is Paris.")])
    http = TestClient(create_agui_app(service, model_factory=lambda: llm))
    thread = Thread(http)
    events = thread.ask("Weather in Paris?")
    assert kinds(operations(events))[0] == "createSurface"
    assert texts(events) == "Here is Paris."
    # the model sees the tool result, A2UI envelope included (AG-UI convention)
    seen = json.dumps(
        [
            p.function_response.response
            for c in llm.requests[1].contents
            for p in c.parts or []
            if p.function_response
        ]
    )
    assert "a2ui_operations" in seen


def test_live_click_reaches_the_model_as_a_user_turn(service: WeatherService) -> None:
    llm = FakeLlm(
        turns=[
            call("get_weather", city="Springfield"),
            say("Which one?"),
            call("get_weather", place_id=4250542, surface_id="picker-1"),
            say("Done."),
        ]
    )
    thread = Thread(TestClient(create_agui_app(service, model_factory=lambda: llm)))
    thread.ask("Weather in Springfield")
    events = thread.click(
        {
            "name": "pick_place",
            "surfaceId": "picker-1",
            "context": {"placeId": 4250542},
        },
        scripted=False,
    )
    said = " ".join(p.text or "" for p in llm.requests[2].contents[-1].parts or [])
    assert said.startswith('[UI action] User performed action "pick_place"')
    assert texts(events) == "Done."


def test_clicks_as_user_turns_rewrites_only_the_synthetic_pair() -> None:
    msgs = [
        {"id": "u", "role": "user", "content": "hi"},
        {
            "id": "a",
            "role": "assistant",
            "content": "",
            "toolCalls": [
                {
                    "id": "c",
                    "type": "function",
                    "function": {"name": "log_a2ui_event", "arguments": "{}"},
                }
            ],
        },
        {
            "id": "r",
            "role": "tool",
            "toolCallId": "c",
            "content": "User performed action",
        },
        {
            "id": "b",
            "role": "assistant",
            "content": "",
            "toolCalls": [
                {
                    "id": "d",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{}"},
                }
            ],
        },
        {"id": "s", "role": "tool", "toolCallId": "d", "content": "{}"},
    ]
    out = clicks_as_user_turns(msgs)
    assert [m["role"] for m in out] == ["user", "user", "assistant", "tool"]
    assert out[1]["content"] == "[UI action] User performed action"


@pytest.mark.parametrize(
    ("name", "ctx", "expected"),
    [
        (
            "pick_place",
            {"placeId": 1, "then": "forecast", "days": 3},
            ("get_forecast", 3),
        ),
        ("pick_place", {"placeId": 1, "then": "weather"}, ("get_weather", None)),
        (
            "set_forecast",
            {"placeId": 1, "days": 16, "units": "imperial"},
            ("get_forecast", 16),
        ),
    ],
)
def test_action_call(
    name: str, ctx: dict[str, Any], expected: tuple[str, int | None]
) -> None:
    text = f'User performed action "{name}" on surface "s-1" (component: b). Context: {json.dumps(ctx)}'
    result = action_call(text)
    assert result is not None
    tool, args = result
    assert (tool, args.get("days")) == expected
    assert args["surface_id"] == "s-1" and args["place_id"] == 1
