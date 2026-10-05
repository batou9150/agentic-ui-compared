# Findings log (working notes, folded into COMPARISON.md at the end)

## core (2026-10-04)

- One Open-Meteo forecast call per place (current + 48 h hourly + 16 days)
  feeds every view; days and units are sliced/converted in core. The 3/7/16
  and °C/°F controls cost zero upstream calls on both sides, so any
  round-trip difference is protocol overhead only.
- Geocoding returns alternate-name matches (Palmyra, Jackson for
  "Springfield"; Paris, Texas for "Paris"): the ambiguity rule (exact name,
  runner-up population >= 10% of top) lives in core.

## MCP Apps (2026-10-04)

- `mcp` 2.3.0 has MCP Apps built in (`mcp.server.apps.Apps`): `@apps.tool`
  stamps `_meta.ui.resourceUri`, `add_html_resource` serves the right MIME
  type and validates that every linked resource exists at startup. Python
  server side of MCP Apps is about 200 lines including docstrings.
- Python SDK 2.x gotcha: the in-process test `Client` must be opened and
  closed in the same task (anyio cancel scopes), so pytest-asyncio async
  generator fixtures do not work; tests open it in the test body.
- View size: each self-contained view is about 235 KB raw / 62 KB gzip
  before any app code, almost all of it the ext-apps App SDK with zod
  bundled. The forecast view with Chart.js is 411 KB / 121 KB gzip. Every
  view ships its own copy (no shared cache across ui:// resources).
- Tested in the official ext-apps basic-host (v2.0.3, built standalone and
  served with Node 25 because the example expects Bun): S1 card, S2 picker
  click -> tools/call -> card + ui/update-model-context, S3 controls
  (16 days, °F) re-call the server, S4 clocks tick in the view. Host dark
  theme reaches the view through host CSS variables; the chart re-reads them
  on `host-context-changed`.
- basic-host has no LLM: `ui/update-model-context` is only displayed
  ("Model Context" panel), nothing consumes it.
- Double iframe sandbox works with zero view-side effort: the view never
  knows about the proxy.

## A2UI (2026-10-04)

- a2ui-agent-sdk 0.7.0 is solid: typed Python builder (nested tree ->
  flat component list), catalog validation with precise errors, A2A part
  helpers, prompt generator. `a2ui.a2a` has no `__init__.py`: import from
  `a2ui.a2a.extension` / `a2ui.a2a.parts`.
- A surface has ONE catalogId, so adding Chart and Clock means a superset
  catalog (basic + 2) declared twice: JSON Schema on the agent (prompt +
  validation) and zod + Lit on the client. Kept in sync by hand.
- The builder does not name the top node `root`; it must be set (`id="root"`).
- Custom `A2uiLitElement`s render in a shadow root while the basic catalog
  renders in light DOM (`renderRoot`, not `this`, to find the canvas).
- Basic `Text` renders Markdown, which needs the separate `@a2ui/markdown-it`
  package (a peer dependency of `@a2ui/lit`, not in the README quick start):
  without it `**bold**` shows raw.
- `@a2ui/*` 0.12 depends on zod 3 while ext-apps 2.x needs zod 4: the two
  clients cannot share a zod version (separate workspaces).
- Only Button emits actions; Button `variant` is static, so a pressed state
  for the 3/7/16 and °C/°F controls cannot be shown (the subtitle shows the
  state instead). MCP view: `aria-pressed`, one line.
- S3 control click = 1 A2A round trip carrying a single `updateDataModel`
  (layout untouched). S2 pick = `updateComponents` + `updateDataModel` on the
  same surface (the picker is replaced in place).
- Prompt cost of LLM-composed UI: the catalog schema in the system prompt is
  42K characters for the full weather catalog, 27K after pruning to the 7
  components a composed layout needs. Paid on every LLM call in Live mode.
- ADK treats `{name}` in a string instruction as state placeholders, which
  clashes with an embedded JSON schema: use an instruction provider.
- Python 3.13 + pytest: two `tests` packages collide; fixed with an
  `__init__.py` per project folder.
- Client bundle (standalone page, Lit renderer + basic catalog + Chart.js +
  A2A client): 673 KB raw / 181 KB gzip, loaded once for all surfaces.

## Comparison harness (2026-10-04)

- First Scripted numbers (local, single run, indicative only): S1 MCP Apps
  236.6 KB / 2 round trips / ~100-130 ms to first render (iframe + sandbox
  proxy + 235 KB HTML parse); A2UI 3.3 KB / 1 round trip / ~20-45 ms.
- The MCP Apps view lifecycle is visible in the log: resources/read and
  tools/call in parallel, then sandbox-resource-ready (the 235 KB HTML goes
  over postMessage), ui/initialize, tool-input, tool-result, size-changed.
- S2/S3 clicks: MCP view -> host -> tools/call -> result -> view +
  ui/update-model-context (2 bridge requests + 1 network round trip);
  A2UI action -> message/stream -> updateComponents/updateDataModel
  (1 round trip, renderer applies it).
- Theming: the MCP host pushes its palette into views via host CSS variables
  (the views look like the host); on the A2UI side the client's CSS variables
  style the renderer's components (the surfaces look like the client).
- Time zones are a trap for LLM-composed charts: Open-Meteo `timezone=auto`
  daily series start on each city's local "today", so a Paris + Tokyo chart
  sharing one label axis can be off by a day. Check the recorded S5.
- Harness: Scripted and Live need different backend instances (fixtures +
  frozen clock vs live API); `make compare` runs both pairs, no protocol
  change needed. macOS bash 3.2 needs care in the launcher script.

## Measurement method (2026-10-04)

- "First render" is measured the same way on both sides: the UI has applied
  the data (A2UI: MessageProcessor processed the messages; MCP Apps: the
  view answered a ping sent after tool-result, i.e. its ontoolresult ran)
  plus two animation frames. Pitfalls met on the way, worth a line:
  - Playwright's fake clock replaces performance.now and rAF: never time
    with it (e2e uses it for S4 clocks, measurements do not).
  - The ext-apps App SDK reports its startup size right after `initialized`;
    that size-changed can reach the host after the host sent the result, so
    "first size change after the result" is not a render signal.
  - The harness ping is excluded from the host-view message counts.
- Bytes are JSON bodies (SSE framing and HTTP headers excluded, same rule on
  both sides). Round trips = HTTP requests to the backend after connection
  setup (MCP initialize / tools/list and the A2A agent card are excluded).

## Real host and Live mode (2026-10-05)

- Claude Desktop through `mcp-remote` (stdio bridge in
  `claude_desktop_config.json`) over an ngrok tunnel: the server log
  shows `initialize` with the `io.modelcontextprotocol/ui` extension, then
  `resources/read` for each view sent in parallel with the first matching
  `tools/call`. The picker click arrives as a `tools/call` carrying
  `_meta.progressToken`, issued by the view through the host.
- Before connecting, the host probes the OAuth discovery endpoints
  (`/.well-known/oauth-*`, `openid-configuration`); 404s are fine for an
  unauthenticated server. It also opens a GET SSE stream on `/mcp`.
- S5 in Claude Desktop: the host drew the two-city chart with its own
  charting, outside the MCP App. Off-script UI moves to the host.
- Live measurements first timed out on S5: A2UI composition takes about 26 s,
  above the harness's default 8 s wait; Live runs now wait up to 120 s.
- With compose retries counted (2026-10-05, 3 Live runs + warm-up): the
  first S5 layout failed catalog validation in 2 of 3 measured runs; one
  retry fixed it each time. The earlier "3 LLM calls vs 2 in the recording"
  was this retry. S5 first render is now 30 to 41 s (median 35 s).
