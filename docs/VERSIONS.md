# Versions

Snapshot taken on **2026-10-04**. Every version below is pinned exactly in the
lockfiles (`uv.lock`, `package-lock.json`). Bumping any of them means
re-running `make test` and `make measure`, then updating this file and the
dated header of `COMPARISON.md`.

## Specifications

| Spec | Version used | Status | Source |
|---|---|---|---|
| MCP Apps (SEP-1865, extension `io.modelcontextprotocol/ui`) | `2026-01-26` | Stable | `specification/2026-01-26/apps.mdx` in modelcontextprotocol/ext-apps @ `82221c0` (tag v2.0.3, 2026-09-25) |
| MCP Apps draft | not used | Draft | `specification/draft/apps.mdx` (adds view-registered tools, sampling, `ui/download-file`) |
| A2UI | `v0.9.1` | Released ("closed") | `specification/v0_9_1/` in a2ui-project/a2ui @ `1444719` (2026-10-02) |
| A2UI v1.0 | not used | Candidate for stable | `specification/v1_0/` (renames messages to `agent_to_renderer` / `renderer_to_agent`) |
| A2UI over A2A extension | `https://a2ui.org/a2a-extension/a2ui/v0.9.1` | Released | `application/a2ui+json` DataParts |

## Python (Python 3.13, managed with uv)

| Package | Version | Used by |
|---|---|---|
| httpx | 0.28.1 | core |
| pydantic | 2.13.5 | core |
| mcp | 2.3.0 | mcp-apps server (`MCPServer` + `mcp.server.apps.Apps`) |
| google-adk | 2.11.0 | a2ui agent |
| a2ui-agent-sdk | 0.7.0 (import `a2ui`) | a2ui agent |
| a2ui-core | 0.2.0 | a2ui agent (transitive, pinned) |
| a2a-sdk | 0.3.26 | a2ui agent (capped `<0.4` by a2ui-agent-sdk 0.7.0) |
| google-genai | 2.28.0 | a2ui agent, compare live bridge |
| pyyaml | 6.0.3 | scenarios loader |
| jsonschema | 4.26.0 | A2UI message validation in tests |
| pytest | 9.1.1 | tests |
| pytest-asyncio | 1.4.0 | tests |
| respx | 0.23.1 | Open-Meteo mocks |
| ruff | 0.16.10 | lint + format |
| mypy | 2.4.0 | types |

## JavaScript / TypeScript (Node 24 LTS in CI, npm workspaces)

| Package | Version | Used by |
|---|---|---|
| @modelcontextprotocol/ext-apps | 2.0.3 | mcp-apps views (App SDK), compare host (`/app-bridge`) |
| @modelcontextprotocol/client | 2.3.0 | compare host (peer of ext-apps 2.x) |
| zod | 4.6.5 | peer of ext-apps, A2UI custom component props |
| @a2ui/web_core | 0.12.0 | a2ui client, compare right pane |
| @a2ui/lit | 0.12.0 | a2ui client, compare right pane |
| @a2a-js/sdk | 0.3.14 | a2ui client (0.3 line, matches a2a-sdk 0.3 on the server) |
| lit | 3.3.3 | A2UI custom components |
| chart.js | 4.5.1 | forecast chart (same library on both sides) |
| vite | 8.3.2 | all front-end builds |
| vite-plugin-singlefile | 2.3.3 | self-contained `ui://` views |
| typescript | 7.0.2 | all TS |
| @playwright/test | 1.63.0 | e2e |
| eslint | 10.12.0 | lint |
| prettier | 3.9.9 | format |

## Model

- Default: `gemini-3.8-flash` on Gemini Enterprise Agent Platform (Google
  Cloud), `GOOGLE_CLOUD_LOCATION=global`. Overridable with `AGENT_MODEL`.
  Listed as the newest Flash model in the platform docs; its launch stage
  (preview or GA) was not confirmed on 2026-10-04. `gemini-3.6-flash` (GA
  since 2026-07-21) is the documented fallback.
- The same model ID drives both panes in Live mode.

## Differences from the original brief

None of these break the plan; they change how it is implemented.

1. **A2UI repository moved**: `github.com/google/A2UI` now redirects to
   `github.com/a2ui-project/a2ui`.
2. **A2UI spec version**: v0.9.1 is the current released version; v1.0 is
   only a candidate and the Google codelab "Frontend Experiences with ADK and
   A2UI" still uses v0.8 (rendered in the ADK dev UI). This repo targets
   v0.9.1 and does not reuse the codelab's message format.
3. **No chart or clock in the A2UI basic catalog** (18 components, none of
   them a chart or a timer). S3 and S4 need a small custom catalog
   (`Chart`, `Clock`) registered in the Lit renderer, with its own catalog
   JSON schema given to the agent. This is the supported extension mechanism,
   but it is extra code on the A2UI side and is counted as such.
4. **Only `Button` emits actions in the A2UI basic catalog**: `ChoicePicker`,
   `Slider` and `TextField` only write to the data model. The S2 picker and
   the S3 controls are therefore Buttons carrying an event context.
5. **MCP Python SDK 2.x**: `FastMCP` was renamed `MCPServer`
   (`mcp.server.mcpserver`) and MCP Apps support is built in
   (`mcp.server.apps`). The Python examples in ext-apps still import
   `mcp.server.fastmcp` and do not run on `mcp` 2.x.
6. **ext-apps 2.x uses the split TS SDK** (`@modelcontextprotocol/client`,
   `core`, `server` 2.x) and is incompatible with `@modelcontextprotocol/sdk`
   1.x.
7. **MCP Apps hosts need two origins**: the stable spec requires a sandbox
   proxy on a separate origin, with the CSP sent as an HTTP header. The
   compare app therefore serves a second port for the sandbox.
8. **Version coupling on the A2UI side**: `a2ui-agent-sdk` 0.7.0 caps
   `a2a-sdk` below 0.4, so the client uses `@a2a-js/sdk` 0.3.x rather than
   the latest 1.x.
9. **Environment variables**: google-genai 2.28 adds
   `GOOGLE_GENAI_USE_ENTERPRISE` next to `GOOGLE_GENAI_USE_VERTEXAI`; when both
   are set and conflict, ENTERPRISE wins. `.env.example` documents only the
   former.
10. **Upstream sample inconsistencies** (to be isolated, not copied): the A2UI
    Lit shell sample sends the v0.8 `userAction` name; the A2A extension doc
    shows a v0.8-shaped component; v0.9.1 schema files carry `v0_9` `$id`s,
    so validation needs an explicit `referencing` registry.
