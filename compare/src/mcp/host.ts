// A minimal MCP Apps host on the official SDKs: @modelcontextprotocol/client
// for the server connection, @modelcontextprotocol/ext-apps/app-bridge for
// views. It renders ui:// views in a double iframe (sandbox proxy on another
// origin, CSP as a header) and relays tool input/results and view requests.
//
// Not supported (compared to real hosts): display modes other than inline,
// ui/open-link, ui/message from the view, permissions (camera, ...),
// view-registered tools, sampling, resource caching across sessions.
import { Client, StreamableHTTPClientTransport, type Transport } from "@modelcontextprotocol/client";
import {
  AppBridge,
  PostMessageTransport,
  RESOURCE_MIME_TYPE,
  getToolUiResourceUri,
  type McpUiHostContext,
  type McpUiStyles,
} from "@modelcontextprotocol/ext-apps/app-bridge";
import { byteLength, type LogEntry } from "../metrics";

type JsonRpc = { id?: unknown; method?: string; result?: unknown; error?: unknown; params?: unknown };
type CallToolResult = Awaited<ReturnType<Client["callTool"]>>;
type Tool = Awaited<ReturnType<Client["listTools"]>>["tools"][number];

export interface HostHooks {
  log(entry: LogEntry): void;
  uiBytes(bytes: number): void;
  rendered(): void;
  modelContext(text: string): void;
}

const HOST_INFO = { name: "compare-harness-host", version: "0.1.0" };

// The host decides the look: these standard MCP Apps style variables are what
// views read. Distinct accent so "who controls the look" is visible.
// Views fall back to their own defaults for the variables a host leaves out.
export const HOST_STYLES: Record<"light" | "dark", Partial<McpUiStyles>> = {
  light: {
    "--color-background-primary": "#ffffff",
    "--color-background-secondary": "#f1f5f9",
    "--color-text-primary": "#0f172a",
    "--color-text-secondary": "#475569",
    "--color-border-primary": "#cbd5e1",
    "--color-ring-primary": "#7c3aed",
    "--border-radius-md": "10px",
  },
  dark: {
    "--color-background-primary": "#0b1020",
    "--color-background-secondary": "#1e293b",
    "--color-text-primary": "#e2e8f0",
    "--color-text-secondary": "#94a3b8",
    "--color-border-primary": "#334155",
    "--color-ring-primary": "#a78bfa",
    "--border-radius-md": "10px",
  },
};

function describe(message: JsonRpc): string {
  if (message.method) return message.method;
  return message.error ? "error" : "result";
}

/** Wraps a transport to log every JSON-RPC message that crosses it. */
class LoggingTransport implements Transport {
  onclose?: () => void;
  onerror?: (error: Error) => void;
  onmessage?: Transport["onmessage"];
  private pending = new Map<unknown, string>();

  constructor(
    private readonly inner: Transport,
    private readonly channel: LogEntry["channel"],
    private readonly log: (entry: LogEntry) => void,
  ) {
    inner.onmessage = (message, extra) => {
      const m = message as JsonRpc;
      const request = m.id !== undefined && !m.method ? this.pending.get(m.id) : undefined;
      this.emit(
        this.channel === "bridge" ? "local" : "in",
        request ? `${request} → ${describe(m)}` : describe(m),
        m,
      );
      this.onmessage?.(message, extra);
    };
    inner.onclose = () => this.onclose?.();
    inner.onerror = (error) => this.onerror?.(error);
  }

  get sessionId() {
    return this.inner.sessionId;
  }

  setProtocolVersion(version: string): void {
    this.inner.setProtocolVersion?.(version);
  }

  start() {
    return this.inner.start();
  }

  close() {
    return this.inner.close();
  }

  send(message: Parameters<Transport["send"]>[0], options?: Parameters<Transport["send"]>[1]) {
    const m = message as JsonRpc;
    if (m.method && m.id !== undefined) this.pending.set(m.id, m.method);
    this.emit(this.channel === "bridge" ? "local" : "out", describe(m), m, this.channel === "network");
    return this.inner.send(message, options);
  }

  private emit(direction: LogEntry["direction"], kind: string, payload: JsonRpc, roundTrip = false): void {
    this.log({
      at: performance.now(),
      direction,
      channel: this.channel,
      kind,
      payload,
      bytes: byteLength(payload),
      roundTrip,
    });
  }
}

export class McpHost {
  private client?: Client;
  tools: Tool[] = [];
  private bridges = new Set<AppBridge>();
  private html = new Map<string, Promise<{ html: string; csp?: unknown }>>();
  private context: McpUiHostContext;

  constructor(
    private readonly serverUrl: string,
    private readonly sandboxUrl: string,
    private readonly hooks: HostHooks,
    theme: "light" | "dark" = "light",
  ) {
    this.context = {
      theme,
      platform: "web",
      displayMode: "inline",
      availableDisplayModes: ["inline"],
      styles: { variables: HOST_STYLES[theme] as McpUiStyles },
    };
  }

  async connect(): Promise<void> {
    const client = new Client(HOST_INFO, {
      capabilities: { extensions: { "io.modelcontextprotocol/ui": { mimeTypes: [RESOURCE_MIME_TYPE] } } },
    });
    const transport = new StreamableHTTPClientTransport(new URL(this.serverUrl));
    await client.connect(
      new LoggingTransport(transport, "network", (e) => {
        // UI payload = ui:// HTML (counted on read) + the data views render.
        const result = (e.payload as { result?: { structuredContent?: unknown } }).result;
        if (e.kind.startsWith("tools/call →") && result?.structuredContent) {
          this.hooks.uiBytes(byteLength(result.structuredContent));
        }
        this.hooks.log(e);
      }),
    );
    this.client = client;
    this.tools = (await client.listTools()).tools;
  }

  /** Tools the model may call (MCP Apps `visibility` must include "model"). */
  get modelTools(): Tool[] {
    return this.tools.filter((t) => {
      const visibility = (t._meta?.ui as { visibility?: string[] } | undefined)?.visibility;
      return !visibility || visibility.includes("model");
    });
  }

  /** Call a tool; if it has a ui:// view, mount it in `container` and feed it. */
  async callTool(
    name: string,
    args: Record<string, unknown>,
    container: HTMLElement,
  ): Promise<CallToolResult> {
    const client = this.client!;
    const tool = this.tools.find((t) => t.name === name);
    const uri = tool ? getToolUiResourceUri(tool) : undefined;
    // Like real hosts, the view loads while the tool runs.
    const view = uri ? this.mountView(uri, container) : undefined;
    const result = await client.callTool({ name, arguments: args });
    if (view) {
      const bridge = await view;
      await bridge.sendToolInput({ arguments: args });
      await bridge.sendToolResult(result);
    } else {
      this.hooks.rendered(); // text-only tool: the text is the render
    }
    return result;
  }

  private readResource(uri: string) {
    // Cached per session (a scenario run starts a new session), so the HTML is
    // counted once per run, as a host with a per-conversation cache would.
    let entry = this.html.get(uri);
    if (!entry) {
      entry = this.client!.readResource({ uri }).then((r) => {
        const content = r.contents[0] as {
          text?: string;
          mimeType?: string;
          _meta?: { ui?: { csp?: unknown } };
        };
        if (content.mimeType !== RESOURCE_MIME_TYPE || typeof content.text !== "string") {
          throw new Error(`${uri} is not an MCP App resource`);
        }
        this.hooks.uiBytes(byteLength(content.text));
        return { html: content.text, csp: content._meta?.ui?.csp };
      });
      this.html.set(uri, entry);
    }
    return entry;
  }

  private async mountView(uri: string, container: HTMLElement): Promise<AppBridge> {
    const { html, csp } = await this.readResource(uri);
    const frame = document.createElement("iframe");
    frame.className = "mcp-view";
    frame.dataset.testid = "mcp-view";
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
    const src = new URL(this.sandboxUrl);
    if (csp) src.searchParams.set("csp", JSON.stringify(csp));
    const proxyReady = new Promise<void>((resolve) => {
      const onMessage = (e: MessageEvent) => {
        if (e.source === frame.contentWindow && e.data?.method === "ui/notifications/sandbox-proxy-ready") {
          window.removeEventListener("message", onMessage);
          resolve();
        }
      };
      window.addEventListener("message", onMessage);
    });
    frame.src = src.href;
    container.append(frame);
    await proxyReady;

    const bridge = new AppBridge(
      this.client!,
      HOST_INFO,
      { serverTools: {}, updateModelContext: { text: {} }, logging: {} },
      { hostContext: this.context },
    );
    let sawResult = false;
    bridge.onsizechange = ({ height }) => {
      if (height !== undefined) frame.style.height = `${Math.ceil(height)}px`;
      if (sawResult) this.hooks.rendered(); // the view laid out the data
    };
    bridge.onupdatemodelcontext = async ({ content }) => {
      const text = (content ?? []).map((c) => (c.type === "text" ? c.text : "")).join("\n");
      if (text) this.hooks.modelContext(text);
      return {};
    };
    const initialized = new Promise<void>((resolve) => (bridge.oninitialized = () => resolve()));
    const transport = new PostMessageTransport(frame.contentWindow!, frame.contentWindow!);
    await bridge.connect(new LoggingTransport(transport, "bridge", (e) => this.hooks.log(e)));
    await bridge.sendSandboxResourceReady({ html });
    await initialized;
    const sendResult = bridge.sendToolResult.bind(bridge);
    bridge.sendToolResult = async (params) => {
      sawResult = true;
      return sendResult(params);
    };
    this.bridges.add(bridge);
    return bridge;
  }

  setTheme(theme: "light" | "dark"): void {
    this.context = { ...this.context, theme, styles: { variables: HOST_STYLES[theme] as McpUiStyles } };
    for (const bridge of this.bridges) bridge.setHostContext(this.context);
  }

  async close(): Promise<void> {
    for (const bridge of this.bridges) await bridge.close().catch(() => undefined);
    this.bridges.clear();
    this.html.clear();
    await this.client?.close().catch(() => undefined);
    this.client = undefined;
  }
}
