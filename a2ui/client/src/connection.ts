// A2A connection to the weather agent, feeding the official A2UI MessageProcessor.
// Every message in and out is reported through `onProtocol` (the compare
// harness turns these into its protocol log and metrics).
import type { MessageSendParams, Part } from "@a2a-js/sdk";
import { A2AClient } from "@a2a-js/sdk/client";
import { MessageProcessor, type ActionPayload, type SurfaceModel } from "@a2ui/web_core/v0_9";
import { weatherCatalog } from "./catalog";

export const A2UI_EXTENSION = "https://a2ui.org/a2a-extension/a2ui/v0.9.1";
export const A2UI_MIME_TYPE = "application/a2ui+json";
const MESSAGE_VERSION = "v0.9.1";

export interface ProtocolEvent {
  at: number; // performance.now()
  direction: "out" | "in";
  kind: string; // "message/stream", "createSurface", "action", "text", ...
  payload: unknown;
  bytes: number;
}

export interface TurnResult {
  text: string[];
  metadata: Record<string, unknown> | undefined;
}

export interface ConnectionHooks {
  onSurface?: (surface: SurfaceModel) => void;
  onText?: (text: string) => void;
  onProtocol?: (event: ProtocolEvent) => void;
  onTurnEnd?: (result: TurnResult) => void;
  onError?: (error: Error) => void;
}

const encoder = new TextEncoder();
const byteLength = (value: unknown) =>
  encoder.encode(typeof value === "string" ? value : JSON.stringify(value)).length;

export class A2uiAgentConnection {
  readonly processor: MessageProcessor;
  private client?: Promise<A2AClient>;
  private contextId?: string;
  private busy: Promise<unknown> = Promise.resolve();

  constructor(
    private readonly agentUrl: string,
    private readonly hooks: ConnectionHooks = {},
  ) {
    // User actions (Button events) come back here and go straight to the agent.
    this.processor = new MessageProcessor([weatherCatalog], (action) => {
      void this.sendAction(action);
    });
    this.processor.onSurfaceCreated((surface) => this.hooks.onSurface?.(surface));
  }

  private getClient(): Promise<A2AClient> {
    this.client ??= A2AClient.fromCardUrl(`${this.agentUrl}/.well-known/agent-card.json`, {
      fetchImpl: (url, init) => {
        const headers = new Headers(init?.headers);
        headers.set("X-A2A-Extensions", A2UI_EXTENSION);
        return fetch(url, { ...init, headers });
      },
    });
    return this.client;
  }

  /** A user prompt. `metadata.scripted` replays a tool call without the LLM. */
  sendText(text: string, metadata?: Record<string, unknown>): Promise<TurnResult> {
    return this.send([{ kind: "text", text }], metadata);
  }

  sendAction(action: ActionPayload): Promise<TurnResult> {
    const data = { version: MESSAGE_VERSION, action };
    this.emit("out", "action", data);
    return this.send([{ kind: "data", data, metadata: { mimeType: A2UI_MIME_TYPE } } as Part]);
  }

  reset(): void {
    this.contextId = undefined;
    for (const id of [...this.processor.getSurfaces().keys()]) {
      this.processor.processMessages([{ version: "v0.9", deleteSurface: { surfaceId: id } }]);
    }
  }

  private send(parts: Part[], metadata?: Record<string, unknown>): Promise<TurnResult> {
    // One turn at a time, in order (a click during a reply waits for it).
    const run = this.busy.then(() => this.stream(parts, metadata));
    this.busy = run.catch(() => undefined);
    return run;
  }

  private async stream(parts: Part[], metadata?: Record<string, unknown>): Promise<TurnResult> {
    const client = await this.getClient();
    const params: MessageSendParams = {
      message: {
        kind: "message",
        messageId: crypto.randomUUID(),
        role: "user",
        parts,
        ...(this.contextId ? { contextId: this.contextId } : {}),
        ...(metadata ? { metadata } : {}),
      },
    };
    this.emit("out", "message/stream", params, true);
    const result: TurnResult = { text: [], metadata: undefined };
    try {
      for await (const event of client.sendMessageStream(params)) {
        this.emit("in", `a2a:${event.kind}`, event, true);
        if (event.kind === "task" || event.kind === "status-update" || event.kind === "message") {
          if ("contextId" in event && event.contextId) this.contextId = event.contextId;
        }
        if (event.kind !== "status-update" || !event.status.message) continue;
        this.handleParts(event.status.message.parts, result);
        if (event.final) result.metadata = event.status.message.metadata;
      }
    } catch (error) {
      this.hooks.onError?.(error as Error);
      throw error;
    }
    this.hooks.onTurnEnd?.(result);
    return result;
  }

  private handleParts(parts: Part[], result: TurnResult): void {
    const a2ui: Record<string, unknown>[] = [];
    for (const part of parts) {
      if (part.kind === "text" && part.text.trim()) {
        result.text.push(part.text);
        this.hooks.onText?.(part.text);
      } else if (part.kind === "data" && part.metadata?.mimeType === A2UI_MIME_TYPE) {
        const message = part.data as Record<string, unknown>;
        this.emit("in", Object.keys(message).find((k) => k !== "version") ?? "a2ui", message);
        a2ui.push(message);
      }
    }
    if (a2ui.length) this.processor.processMessages(a2ui as never);
  }

  private emit(direction: "in" | "out", kind: string, payload: unknown, envelope = false): void {
    if (!this.hooks.onProtocol) return;
    // Bytes are counted on the A2A envelopes (what goes over the wire); the
    // A2UI messages and actions inside them are logged for readability only.
    this.hooks.onProtocol({
      at: performance.now(),
      direction,
      kind,
      payload,
      bytes: envelope ? byteLength(payload) : 0,
    });
  }
}
