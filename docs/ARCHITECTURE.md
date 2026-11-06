# Architecture

One weather domain, two UI protocols, one harness to compare them.

```mermaid
flowchart LR
  subgraph core["core/ (shared, the only business logic)"]
    svc["WeatherService<br/>geocode, ambiguity rule, current, daily, hourly,<br/>local time, WMO mapping, units, TTL cache"]
    om[("Open-Meteo<br/>live or recorded fixtures")]
    svc --> om
  end

  subgraph mcp["mcp-apps/"]
    server["MCP server (Python, mcp 2.3)<br/>tools + ui:// resources"]
    views["3 views (TS, Vite single-file HTML)<br/>ext-apps App SDK"]
    views -. "built into" .-> server
  end

  subgraph a2ui["a2ui/"]
    agent["ADK agent (Python) over A2A<br/>tools, designed surfaces,<br/>executor, Gemini in Live mode"]
    client["Web client<br/>@a2ui/lit renderer + Chart/Clock"]
  end

  subgraph compare["compare/ (harness, :8080)"]
    host["Minimal MCP Apps host<br/>client + AppBridge + agent loop"]
    sandbox["Sandbox proxy origin (:8081)<br/>CSP as HTTP header"]
    pane["A2UI pane<br/>(the a2ui client)"]
    llm["/api/llm<br/>Gemini proxy"]
  end

  server --> svc
  agent --> svc
  host -- "Streamable HTTP, JSON-RPC" --> server
  host -- "postMessage JSON-RPC" --> sandbox
  pane -- "A2A JSON-RPC + SSE" --> agent
  host --> llm
```

## Rule of the repo

Business logic lives only in `core/`. Both implementation folders hold
protocol and UI code only: both servers call the same `WeatherService`
methods and receive the same Pydantic models. The ambiguity rule ("Springfield"
needs a picker, "Paris" does not), unit conversion and day slicing are in
core, so the 3/7/16 days and °C/°F controls never trigger a new Open-Meteo
call on either side.

## MCP Apps: the server ships the UI

Each UI tool carries `_meta.ui.resourceUri` pointing to a `ui://` resource
(`text/html;profile=mcp-app`). The host reads the HTML, renders it in a
sandboxed iframe, and relays tool input and results to it over JSON-RPC on
`postMessage`. The view can call tools back through the host.

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant H as Host (+ its LLM)
  participant P as Sandbox proxy (other origin)
  participant V as View (ui://weather/current.html)
  participant S as MCP server
  U->>H: "Weather in Springfield"
  H->>S: tools/call get_weather {city}
  H->>S: resources/read ui://weather/current.html
  S-->>H: HTML (235 KB, self-contained)
  H->>P: load sandbox.html (CSP header)
  P-->>H: sandbox-proxy-ready
  H->>P: sandbox-resource-ready {html}
  P->>V: srcdoc
  V->>H: ui/initialize
  S-->>H: result {content: summary, structuredContent: candidates}
  H->>V: tool-input, tool-result
  V-->>U: picker
  U->>V: click "Illinois"
  V->>H: tools/call get_weather {place_id}
  H->>S: tools/call
  S-->>H: result
  H-->>V: result
  V->>H: ui/update-model-context "The user picked ..."
```

## A2UI: the agent describes the UI

The agent sends declarative JSON messages (`createSurface`,
`updateComponents`, `updateDataModel`) as A2A DataParts. The client renders
them with its own trusted component catalog and sends user actions back as
A2A messages.

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant C as Client (A2UI renderer)
  participant A as ADK agent (A2A executor)
  participant T as Tools (core)
  U->>C: "Weather in Springfield"
  C->>A: message/stream (X-A2A-Extensions: a2ui v0.9.1)
  A->>T: get_weather {city}
  T-->>A: Resolution (5 candidates)
  A-->>C: createSurface, updateComponents (Buttons with actions)
  C-->>U: picker (rendered from the client's catalog)
  U->>C: click "Illinois"
  C->>A: message/stream {action: pick_place, context: {placeId}}
  A->>T: city_weather(place_id)
  A-->>C: updateComponents (card) + updateDataModel (values)
```

In Live mode the agent runs Gemini: tools that have a designed surface render
it as soon as they return (the model only reads the text summary, as with MCP
Apps); for requests no surface was designed for, the model composes a layout
itself in A2UI JSON, validated against the catalog with one retry. User
actions never go through the model: they are handled by the executor, like
an MCP App view calling a tool directly.

## A2UI over AG-UI: same agent, another transport

AG-UI is a transport, not a UI format: it streams typed events between an
agent and a frontend, and can carry A2UI. The same agent process serves it
under `/agui` (`a2ui_agent/agui.py`, built on `ag_ui_adk`), and the harness
can switch the A2UI pane to it with `?a2ui=agui`. The renderer, catalog,
tools, surfaces and model are the same; what changes follows the AG-UI
conventions:

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant C as Client (A2UI renderer + @ag-ui/client)
  participant R as Relay (Node, @ag-ui/a2ui-middleware)
  participant A as ag_ui_adk + ADK agent
  participant M as Model (Gemini or replay)
  U->>C: "Weather in Springfield"
  C->>R: POST run (whole history)
  R->>A: POST run
  A->>M: prompt
  M-->>A: call get_weather {city}
  A-->>R: TOOL_CALL_RESULT {summary, a2ui_operations}
  R-->>C: TOOL_CALL_RESULT + ACTIVITY_SNAPSHOT a2ui-surface
  C-->>U: picker (same catalog)
  U->>C: click "Illinois"
  C->>R: POST run, forwardedProps.a2uiAction
  R->>A: + synthetic log_a2ui_event call and result
  Note over A: shim: the pair becomes a user message<br/>(ag_ui_adk 0.12 drops it otherwise)
  A->>M: "[UI action] User performed action pick_place ..."
  M-->>A: call get_weather {place_id, surface_id: picker-1}
  A-->>R: TOOL_CALL_RESULT (picker redrawn in place)
  R-->>C: ACTIVITY_SNAPSHOT
```

- **Surfaces travel in tool results**, as an `a2ui_operations` envelope that
  the middleware turns into `a2ui-surface` activity events. The model reads
  the whole tool result, A2UI included.
- **A composed layout (S5) goes through a `compose_ui` tool**: the middleware
  does not read A2UI written in a text reply. Validation errors come back as
  tool errors, and the model retries within the same run.
- **A click is a turn of the model**: the middleware sends it as a synthetic
  `log_a2ui_event` tool call; the model answers with a tool call carrying the
  surface id to redraw. `ag_ui_adk` 0.12 skips that pair ("no matching pending
  tool calls"), so an ASGI shim rewrites it as a user message with the same
  text.
- **The middleware needs Node** (it imports `crypto`), so the browser talks
  to a relay in the compare server (`compare/server/agui.ts`), the role a
  CopilotKit runtime plays in a real deployment. The relay adds the run's LLM
  usage as a `CUSTOM` event.
- **Scripted mode** swaps Gemini for a replay model that makes the scenario's
  tool call (and, after a click, the call the click asks for), so a run still
  goes through the agent loop, the events and the middleware with no LLM.

## The weather catalog (A2UI)

The A2UI basic catalog has no chart and no clock, and a surface declares a
single `catalogId`. The repo therefore defines one catalog, the basic one
plus `Chart` and `Clock`, twice: as JSON Schema on the agent side (prompt and
validation, `a2ui/agent/src/a2ui_agent/catalog.py`) and as zod schemas + Lit
elements on the client (`a2ui/client/src/catalog.ts`).

## The comparison harness

```mermaid
flowchart TB
  ui["compare UI :8080<br/>scenario picker, mode, theme, Run on both"]
  subgraph scripted["Scripted mode (no LLM, fixtures, frozen clock)"]
    m1["MCP server :3101"]
    a1["A2UI agent :10102"]
  end
  subgraph live["Live mode (Gemini on both sides, live API)"]
    m2["MCP server :3001"]
    a2["A2UI agent :10002"]
    g["Gemini (same model ID)"]
  end
  relay["/api/agui relay<br/>(A2UI pane over AG-UI)"]
  ui --> m1 & a1
  ui --> m2 & a2
  ui -.-> relay -.-> a1 & a2
  ui -- "/api/llm (MCP host loop)" --> g
  a2 -- "ADK" --> g
```

- **Scripted**: each scenario (`scenarios/*.yaml`) lists the tool calls to
  replay and the clicks to perform. The MCP pane sends real `tools/call`; the
  A2UI pane sends the same call as message metadata, which the executor runs
  without the LLM (over AG-UI: `forwardedProps.scripted`, answered by the
  replay model). Both backends read the same fixtures. Clicks are real
  clicks in the rendered UI (Playwright or a human).
- **Live**: the prompt goes to both sides. The MCP pane runs its own small
  agent loop over the MCP tools (`compare/src/mcp/agent.ts`), calling the
  same Gemini model as the ADK agent through a server-side proxy.
- **Inspector**: every message is logged with direction, size and time:
  JSON-RPC to the MCP server, host-view `postMessage` traffic, A2A envelopes,
  A2UI messages and actions. Metrics are computed from that log.

## What the minimal MCP Apps host does not do

Compared with real hosts (Claude, ChatGPT, VS Code, ...): inline display mode
only, no `ui/open-link`, no `ui/message` from views, no permissions (camera,
microphone, ...), no view-registered tools or sampling (draft spec), no
resource caching across sessions, no persistence. It does implement the
stable spec's security model: separate sandbox origin, CSP built from
`_meta.ui.csp` and sent as a header, and tool visibility filtering.
