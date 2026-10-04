// Left pane: chat transcript + the minimal MCP Apps host.
import { LitElement, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { MetricsCollector } from "../metrics";
import type { Step } from "../scenarios";
import { McpAgent } from "../mcp/agent";
import { McpHost } from "../mcp/host";
import type { Pane, Theme } from "./types";

@customElement("mcp-pane")
export class McpPane extends LitElement implements Pane {
  @property({ attribute: false }) config!: { mcpUrl: string; sandboxUrl: string };
  @state() private connected = false;
  readonly metrics = new MetricsCollector("mcp");
  private host?: McpHost;
  private agent?: McpAgent;
  private theme: Theme = "light";

  protected createRenderRoot() {
    return this; // light DOM: page styles and Playwright selectors apply
  }

  private get transcript(): HTMLElement {
    return this.querySelector("[data-testid=transcript-mcp]")!;
  }

  async connect(): Promise<void> {
    this.host = new McpHost(
      this.config.mcpUrl,
      this.config.sandboxUrl,
      {
        log: (e) => {
          this.metrics.record(e);
          this.dispatchEvent(new CustomEvent("log"));
        },
        uiBytes: (n) => this.metrics.addUiBytes(n),
        rendered: () => {
          this.metrics.markRendered();
          this.dispatchEvent(new CustomEvent("log")); // refresh the inspector
        },
        modelContext: (text) => this.agent?.addModelContext(text),
      },
      this.theme,
    );
    await this.host.connect();
    this.agent = new McpAgent(this.host, {
      text: (t) => this.line("agent", t),
      usage: (c, i, o) => this.metrics.addLlmUsage(c, i, o),
    });
    this.connected = true;
  }

  async reset(): Promise<void> {
    await this.host?.close();
    this.host = undefined;
    await this.updateComplete;
    this.transcript.replaceChildren();
    this.connected = false;
    await this.connect();
  }

  private line(kind: "user" | "agent" | "error", text: string): void {
    const p = document.createElement("p");
    p.className = `msg ${kind}`;
    p.dataset.testid = `msg-${kind}`;
    p.textContent = text;
    this.transcript.append(p);
  }

  async runStep(step: Step, prompt: string, first: boolean): Promise<void> {
    if (first) this.line("user", prompt);
    if (step.kind !== "tool") return; // clicks happen in the view; no compose on this side
    try {
      const result = await this.host!.callTool(step.tool, step.args, this.transcript);
      // A real host shows the model's reply; in Scripted mode there is no model,
      // so the tool's text content stands in for it (same as the A2UI side).
      const text = (result.content ?? []).map((c) => (c.type === "text" ? c.text : "")).join("\n");
      if (text) this.line(result.isError ? "error" : "agent", text);
    } catch (error) {
      this.line("error", (error as Error).message);
    }
  }

  async ask(prompt: string): Promise<void> {
    this.line("user", prompt);
    try {
      await this.agent!.ask(prompt, this.transcript);
    } catch (error) {
      this.line("error", (error as Error).message);
    }
  }

  setTheme(theme: Theme): void {
    this.theme = theme;
    this.host?.setTheme(theme); // the host pushes its look into every view
  }

  render() {
    return html`<div
      class="transcript"
      data-testid="transcript-mcp"
      ?data-connected=${this.connected}
    ></div>`;
  }
}
