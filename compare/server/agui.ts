// POST /api/agui/{scripted|live}: the AG-UI relay for the A2UI pane.
//
// It is the Node hop a real AG-UI deployment has (the role CopilotKit's
// runtime plays): @ag-ui/a2ui-middleware needs Node, so the browser posts its
// RunAgentInput here, the relay runs the agent's AG-UI endpoint through the
// middleware, and streams the resulting events back as SSE. The middleware
// turns tool results carrying `a2ui_operations` into `a2ui-surface` activity
// events, and a click (forwardedProps.a2uiAction) into a turn of the agent.
//
// The relay adds one CUSTOM event before RUN_FINISHED with the run's LLM usage
// (the A2A side carries it in its final message metadata).
import { A2UIMiddleware } from "@ag-ui/a2ui-middleware";
import { EventType, HttpAgent, type BaseEvent, type RunAgentInput } from "@ag-ui/client";
import { EventEncoder } from "@ag-ui/encoder";
import type { IncomingMessage, ServerResponse } from "node:http";

export const USAGE_EVENT = "weather/usage"; // same name as in @weather/a2ui-client
const MAX_BODY = 5_000_000; // AG-UI resends the whole history on every run

function fail(res: ServerResponse, status: number, error: string): void {
  res.statusCode = status;
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify({ error }));
}

/** `agents` maps a mode to the A2UI agent's base URL (its AG-UI app is under /agui/). */
export function aguiRelay(agents: Record<string, string>, env: Record<string, string>) {
  const allowedOrigins = new Set(
    [env.COMPARE_PORT || "8080"].flatMap((port) => [`http://localhost:${port}`, `http://127.0.0.1:${port}`]),
  );
  return async (req: IncomingMessage, res: ServerResponse) => {
    const mode = (req.url ?? "").replace(/^\/+/, "").split(/[/?]/)[0];
    const base = agents[mode];
    if (!base) return fail(res, 404, "Unknown mode.");
    if (req.method !== "POST") return fail(res, 405, "Method not allowed.");
    if (!allowedOrigins.has(req.headers.origin ?? "")) return fail(res, 403, "Forbidden origin.");
    let body = "";
    for await (const chunk of req) {
      body += chunk;
      if (body.length > MAX_BODY) return fail(res, 413, "Request body too large.");
    }
    let input: RunAgentInput;
    try {
      input = JSON.parse(body) as RunAgentInput;
    } catch {
      return fail(res, 400, "Invalid JSON.");
    }

    const agent = new HttpAgent({
      url: `${base}/agui/`,
      threadId: input.threadId,
      initialMessages: input.messages,
      initialState: input.state,
    });
    agent.use(new A2UIMiddleware());
    const encoder = new EventEncoder({ accept: req.headers.accept });
    res.writeHead(200, { "content-type": encoder.getContentType(), "cache-control": "no-cache" });
    const write = (event: BaseEvent) => res.write(encoder.encode(event));

    let finished: BaseEvent | undefined;
    try {
      await agent.runAgent(
        {
          runId: input.runId,
          tools: input.tools,
          context: input.context,
          forwardedProps: input.forwardedProps,
        },
        {
          onEvent: ({ event }) => {
            if (event.type === EventType.RUN_FINISHED) finished = event;
            else write(event);
          },
        },
      );
      const usage = await fetch(`${base}/agui/usage?threadId=${encodeURIComponent(input.threadId)}`)
        .then((r) => r.json())
        .catch(() => undefined);
      if (usage) write({ type: EventType.CUSTOM, name: USAGE_EVENT, value: usage } as BaseEvent);
      if (finished) write(finished);
    } catch (error) {
      console.error("[api/agui]", error);
      write({
        type: EventType.RUN_ERROR,
        message: "The AG-UI run failed; see the dev server log.",
      } as BaseEvent);
    }
    res.end();
  };
}
