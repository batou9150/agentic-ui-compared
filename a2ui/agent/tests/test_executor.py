"""End to end over A2A JSON-RPC: scripted steps, user actions, live with a fake LLM."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from a2ui_agent.agent import build_agent
from a2ui_agent.catalog import WEATHER_CATALOG_ID
from a2ui_agent.executor import WeatherAgentExecutor
from a2ui_agent.server import agent_card, create_app
from starlette.testclient import TestClient
from weather_core import WeatherService

from .fake_llm import FakeLlm, call, say
from .spec import assert_spec_valid

EXT = "https://a2ui.org/a2a-extension/a2ui/v0.9.1"


class Agent:
    """Tiny A2A JSON-RPC client over the Starlette test client."""

    def __init__(self, http: TestClient, a2ui: bool = True) -> None:
        self.http, self.a2ui, self.n = http, a2ui, 0
        self.context_id: str | None = None

    def send(
        self, parts: list[dict[str, Any]], metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.n += 1
        message: dict[str, Any] = {
            "role": "user",
            "parts": parts,
            "messageId": f"m{self.n}",
            "kind": "message",
        }
        if metadata:
            message["metadata"] = metadata
        if self.context_id:
            message["contextId"] = self.context_id
        headers = {"X-A2A-Extensions": EXT} if self.a2ui else {}
        body = {
            "jsonrpc": "2.0",
            "id": self.n,
            "method": "message/send",
            "params": {"message": message},
        }
        r = self.http.post("/", json=body, headers=headers)
        assert r.status_code == 200, r.text
        result: dict[str, Any] = r.json()["result"]
        self.context_id = result["contextId"]
        return result

    def text(self, prompt: str, **meta: Any) -> dict[str, Any]:
        return self.send([{"kind": "text", "text": prompt}], meta or None)

    def action(
        self, name: str, surface_id: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        action = {
            "name": name,
            "surfaceId": surface_id,
            "sourceComponentId": "b",
            "timestamp": "2026-10-04T12:00:00Z",
            "context": context,
        }
        return self.send(
            [
                {
                    "kind": "data",
                    "data": {"version": "v0.9.1", "action": action},
                    "metadata": {"mimeType": "application/a2ui+json"},
                }
            ]
        )


def a2ui_messages(task: dict[str, Any]) -> list[dict[str, Any]]:
    parts = [
        p
        for m in [*task.get("history", []), task["status"].get("message") or {}]
        if m.get("role") == "agent"
        for p in m.get("parts", [])
    ]
    return [p["data"] for p in parts if p["kind"] == "data"]


def final_text(task: dict[str, Any]) -> str:
    return " ".join(
        p["text"] for p in task["status"]["message"]["parts"] if p["kind"] == "text"
    )


@pytest.fixture
def make_agent(service: WeatherService) -> Iterator[Any]:
    clients: list[TestClient] = []

    def _make(
        turns: list[Any] | None = None, a2ui: bool = True
    ) -> tuple[Agent, WeatherAgentExecutor]:
        card = agent_card("http://localhost:10002")
        executor = WeatherAgentExecutor(service, card)
        if turns is not None:
            executor._agent_factory = lambda: build_agent(
                executor.tools, FakeLlm(turns=turns)
            )
        http = TestClient(create_app(executor=executor))
        clients.append(http)
        return Agent(http, a2ui), executor

    yield _make
    for c in clients:
        c.close()


def test_agent_card_advertises_a2ui(make_agent: Any) -> None:
    agent, _ = make_agent()
    card = agent.http.get("/.well-known/agent-card.json").json()
    ext = card["capabilities"]["extensions"][0]
    assert ext["uri"] == EXT
    assert WEATHER_CATALOG_ID in ext["params"]["supportedCatalogIds"]


def test_scripted_weather_card(make_agent: Any) -> None:
    agent, _ = make_agent()
    task = agent.text(
        "What's the weather in Paris?",
        scripted={"tool": "get_weather", "args": {"city": "Paris"}},
    )
    msgs = a2ui_messages(task)
    assert_spec_valid(msgs)
    assert [next(k for k in m if k != "version") for m in msgs] == [
        "createSurface",
        "updateComponents",
        "updateDataModel",
    ]
    assert msgs[0]["createSurface"]["surfaceId"] == "weather-1"
    assert final_text(task).startswith("Paris")
    assert task["status"]["message"]["metadata"]["path"] == "scripted"


def test_scripted_picker_then_pick(make_agent: Any) -> None:
    agent, executor = make_agent()
    task = agent.text(
        "Weather in Springfield",
        scripted={"tool": "get_weather", "args": {"city": "Springfield"}},
    )
    picker = a2ui_messages(task)
    assert picker[0]["createSurface"]["surfaceId"] == "picker-1"
    button = next(
        c
        for c in picker[1]["updateComponents"]["components"]
        if c["component"] == "Button"
        and c["action"]["event"]["context"]["placeId"] == 4250542
    )
    task = agent.action("pick_place", "picker-1", button["action"]["event"]["context"])
    msgs = a2ui_messages(task)
    assert_spec_valid(msgs)
    assert [next(k for k in m if k != "version") for m in msgs] == [
        "updateComponents",
        "updateDataModel",
    ]
    assert (
        msgs[1]["updateDataModel"]["value"]["place"]
        == "Springfield, Illinois, United States"
    )
    assert task["status"]["message"]["metadata"]["path"] == "action"
    assert "picked Springfield, Illinois" in executor._ui_notes[agent.context_id][0]


def test_forecast_control_is_a_data_update(make_agent: Any) -> None:
    agent, _ = make_agent()
    task = agent.text(
        "Forecast for Lyon",
        scripted={"tool": "get_forecast", "args": {"city": "Lyon", "days": 7}},
    )
    place_id = a2ui_messages(task)[2]["updateDataModel"]["value"]["placeId"]
    task = agent.action(
        "set_forecast",
        "forecast-1",
        {"placeId": place_id, "days": 16, "units": "imperial"},
    )
    msgs = a2ui_messages(task)
    assert len(msgs) == 1 and "updateDataModel" in msgs[0]
    value = msgs[0]["updateDataModel"]["value"]
    assert value["days"] == 16 and value["chart"]["leftUnit"] == "°F"


def test_scripted_world_clock(make_agent: Any) -> None:
    agent, _ = make_agent()
    task = agent.text(
        "Time and weather",
        scripted={
            "tool": "get_world_clock",
            "args": {"cities": ["Paris", "Tokyo", "New York"]},
        },
    )
    msgs = a2ui_messages(task)
    assert_spec_valid(msgs)
    comps = msgs[1]["updateComponents"]["components"]
    assert sum(c["component"] == "Clock" for c in comps) == 3


def test_text_only_client_gets_no_a2ui(make_agent: Any) -> None:
    agent, _ = make_agent(a2ui=False)
    task = agent.text(
        "Weather in Paris", scripted={"tool": "get_weather", "args": {"city": "Paris"}}
    )
    assert a2ui_messages(task) == []
    assert "Paris" in final_text(task)


def test_unknown_city_is_a_text_error(make_agent: Any) -> None:
    agent, _ = make_agent()
    task = agent.text("?", scripted={"tool": "get_weather", "args": {"city": "Zzzqqx"}})
    assert "No location found" in final_text(task)


def test_live_tool_call_renders_designed_surface(make_agent: Any) -> None:
    agent, _ = make_agent(
        turns=[call("get_weather", city="Tokyo"), say("Here is the weather in Tokyo.")]
    )
    task = agent.text("Weather in Tokyo?")
    msgs = a2ui_messages(task)
    assert msgs and msgs[0]["createSurface"]["surfaceId"] == "weather-1"
    assert final_text(task) == "Here is the weather in Tokyo."
    usage = task["status"]["message"]["metadata"]["usage"]
    assert usage["llm_calls"] == 2 and usage["input_tokens"] == 200


def test_live_ui_notes_reach_the_model(make_agent: Any) -> None:
    agent, executor = make_agent(turns=[say("Pick one."), say("Noted.")])
    agent.text("Weather in Springfield?")
    executor._ui_notes[agent.context_id].append(
        "The user picked Springfield, Illinois."
    )
    agent.text("And tomorrow?")
    last_request = executor.runner().agent.model.requests[-1]  # type: ignore[union-attr]
    assert "[UI context] The user picked Springfield, Illinois." in json.dumps(
        [c.model_dump(mode="json") for c in last_request.contents]
    )


COMPOSED = {
    "version": "v0.9.1",
    "createSurface": {"surfaceId": "compare-1", "catalogId": WEATHER_CATALOG_ID},
}
COMPONENTS = {
    "version": "v0.9.1",
    "updateComponents": {
        "surfaceId": "compare-1",
        "components": [
            {"id": "root", "component": "Column", "children": ["chart"]},
            {
                "id": "chart",
                "component": "Chart",
                "labels": ["Mon", "Tue"],
                "series": [
                    {
                        "label": "Paris",
                        "kind": "line",
                        "axis": "left",
                        "values": [20, 21],
                    }
                ],
            },
        ],
    },
}
BROKEN = {
    "version": "v0.9.1",
    "updateComponents": {
        "surfaceId": "compare-1",
        "components": [{"id": "root", "component": "Chart"}],
    },
}


def _wrap(*msgs: dict[str, Any]) -> str:
    return f"Here you go.\n<a2ui-json>{json.dumps(list(msgs))}</a2ui-json>"


def test_live_composed_layout_is_validated(make_agent: Any) -> None:
    agent, _ = make_agent(
        turns=[
            call("get_forecast", city="Paris", days=2, show_ui=False),
            say(_wrap(COMPOSED, COMPONENTS)),
        ]
    )
    task = agent.text("Compare Paris and Tokyo on one chart")
    msgs = a2ui_messages(task)
    assert [m["createSurface"]["surfaceId"] for m in msgs if "createSurface" in m] == [
        "compare-1"
    ]
    assert task["status"]["message"]["metadata"]["usage"]["compose_retries"] == 0


def test_live_invalid_layout_gets_one_retry(make_agent: Any) -> None:
    agent, _ = make_agent(
        turns=[say(_wrap(COMPOSED, BROKEN)), say(_wrap(COMPOSED, COMPONENTS))]
    )
    task = agent.text("Compare Paris and Tokyo on one chart")
    assert task["status"]["message"]["metadata"]["usage"]["compose_retries"] == 1
    assert any("updateComponents" in m for m in a2ui_messages(task))


def test_live_gives_up_after_one_retry(make_agent: Any) -> None:
    agent, _ = make_agent(
        turns=[say(_wrap(COMPOSED, BROKEN)), say(_wrap(COMPOSED, BROKEN))]
    )
    task = agent.text("Compare Paris and Tokyo on one chart")
    assert a2ui_messages(task) == []
    assert "invalid" in final_text(task)


def test_scripted_compose_replays_a_validated_layout(make_agent: Any) -> None:
    agent, _ = make_agent()
    recorded = {"text": "Both cities.", "messages": [COMPOSED, COMPONENTS]}
    task = agent.text("Compare", scripted={"compose": recorded})
    assert [m.get("createSurface", {}).get("surfaceId") for m in a2ui_messages(task)][
        0
    ] == "compare-1"
    assert final_text(task) == "Both cities."


def test_scripted_compose_rejects_invalid_layout(make_agent: Any) -> None:
    agent, _ = make_agent()
    task = agent.text("Compare", scripted={"compose": {"messages": [COMPOSED, BROKEN]}})
    assert a2ui_messages(task) == []
    assert "recorded layout is invalid" in final_text(task)
