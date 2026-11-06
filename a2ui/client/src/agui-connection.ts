// AG-UI connection to the same weather agent, feeding the same A2UI
// MessageProcessor and catalog as the A2A connection: only the transport changes.
//
// It talks to an AG-UI endpoint that runs @ag-ui/a2ui-middleware (the compare
// harness relay): surfaces arrive as `a2ui-surface` ACTIVITY_SNAPSHOT events,
// and a click is sent the AG-UI way, as forwardedProps.a2uiAction, which the
// agent answers as a turn of its model.
import { EventType, HttpAgent, type BaseEvent } from "@ag-ui/client";
import { MessageProcessor, type ActionPayload } from "@a2ui/web_core/v0_9";
import { weatherCatalog } from "./catalog";
import type { AgentConnection, ConnectionHooks, TurnResult } from "./connection";

const encoder = new TextEncoder();
const byteLength = (value: unknown) =>
  encoder.encode(typeof value === "string" ? value : JSON.stringify(value)).length;

/** Custom event the harness relay adds before RUN_FINISHED (the run's LLM usage). */
export const USAGE_EVENT = "weather/usage";
const A2UI_ACTIVITY = "a2ui-surface";
const A2UI_OPERATIONS_KEY = "a2ui_operations";

export class AguiAgentConnection implements AgentConnection {
  readonly processor: MessageProcessor;
  /**
   * Scripted mode: clicks carry `forwardedProps.scripted`, so the agent answers
   * them with its replay model instead of Gemini (still one agent turn).
   */
  scriptedClicks = false;
  private agent: HttpAgent;
  private busy: Promise<unknown> = Promise.resolve();
  private seen = new Set<string>(); // activity snapshots already applied

  constructor(
    private readonly url: string,
    private readonly hooks: ConnectionHooks = {},
  ) {
    this.processor = new MessageProcessor([weatherCatalog], (action) => {
      void this.sendAction(action);
    });
    this.processor.onSurfaceCreated((surface) => this.hooks.onSurface?.(surface));
    this.agent = this.newAgent();
  }

  private newAgent(): HttpAgent {
    return new HttpAgent({
      url: this.url,
      threadId: crypto.randomUUID(),
      // Logs the exact request body: the whole history is resent every run.
      fetch: (input, init) => {
        const body = typeof init?.body === "string" ? init.body : "";
        this.emit("out", "run", body ? JSON.parse(body) : {}, byteLength(body));
        return fetch(input, init);
      },
    });
  }

  /** No handshake in AG-UI (no agent card): nothing to fetch up front. */
  async ready(): Promise<void> {}

  /** A user prompt. `metadata.scripted` replays a tool call without the LLM. */
  sendText(text: string, metadata?: Record<string, unknown>): Promise<TurnResult> {
    this.agent.addMessage({ id: crypto.randomUUID(), role: "user", content: text });
    const scripted = metadata?.scripted;
    return this.send(scripted ? { scripted } : {});
  }

  sendAction(action: ActionPayload): Promise<TurnResult> {
    const userAction = {
      name: action.name,
      surfaceId: action.surfaceId,
      sourceComponentId: action.sourceComponentId,
      context: action.context,
    };
    this.emit("out", "action", userAction, 0);
    return this.send({
      a2uiAction: { userAction },
      ...(this.scriptedClicks ? { scripted: { click: true } } : {}),
    });
  }

  reset(): void {
    this.agent = this.newAgent();
    this.seen.clear();
    for (const id of [...this.processor.getSurfaces().keys()]) {
      this.processor.processMessages([{ version: "v0.9", deleteSurface: { surfaceId: id } }]);
    }
  }

  private send(forwardedProps: Record<string, unknown>): Promise<TurnResult> {
    // One run at a time, in order (a click during a reply waits for it).
    const run = this.busy.then(() => this.run(forwardedProps));
    this.busy = run.catch(() => undefined);
    return run;
  }

  private async run(forwardedProps: Record<string, unknown>): Promise<TurnResult> {
    const result: TurnResult = { text: [], metadata: undefined };
    let text = "";
    try {
      await this.agent.runAgent(
        { forwardedProps },
        {
          onEvent: ({ event }) => {
            this.emit("in", `agui:${event.type}`, event, byteLength(event));
            switch (event.type) {
              case EventType.ACTIVITY_SNAPSHOT:
                this.applyActivity(event);
                break;
              case EventType.TEXT_MESSAGE_CONTENT:
                text += (event as BaseEvent & { delta: string }).delta;
                break;
              case EventType.TEXT_MESSAGE_END:
                if (text.trim()) {
                  result.text.push(text);
                  this.hooks.onText?.(text);
                }
                text = "";
                break;
              case EventType.CUSTOM: {
                const custom = event as BaseEvent & { name: string; value: unknown };
                if (custom.name === USAGE_EVENT) result.metadata = { usage: custom.value };
                break;
              }
            }
          },
        },
      );
    } catch (error) {
      this.hooks.onError?.(error as Error);
      throw error;
    }
    this.hooks.onTurnEnd?.(result);
    return result;
  }

  private applyActivity(event: BaseEvent): void {
    const activity = event as BaseEvent & {
      activityType: string;
      messageId: string;
      content: Record<string, unknown>;
    };
    if (activity.activityType !== A2UI_ACTIVITY) return;
    const ops = activity.content?.[A2UI_OPERATIONS_KEY];
    if (!Array.isArray(ops) || !ops.length) return; // a lifecycle status, not a surface
    const key = `${activity.messageId}:${JSON.stringify(ops)}`;
    if (this.seen.has(key)) return; // a replacing snapshot with the same content
    this.seen.add(key);
    for (const op of ops as Record<string, unknown>[]) {
      this.emit("in", Object.keys(op).find((k) => k !== "version") ?? "a2ui", op, 0);
    }
    this.processor.processMessages(ops as never);
    const rendered = this.hooks.onRendered;
    if (rendered) requestAnimationFrame(() => requestAnimationFrame(rendered));
  }

  private emit(direction: "in" | "out", kind: string, payload: unknown, bytes: number): void {
    // Bytes are counted on the AG-UI request bodies and events (JSON), like
    // the A2A envelopes; the A2UI messages inside are logged for readability.
    this.hooks.onProtocol?.({ at: performance.now(), direction, kind, payload, bytes });
  }
}
