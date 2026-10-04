// Right pane: the A2UI chat (official Lit renderer) connected to the ADK agent.
import "@weather/a2ui-client/src/chat";
import type { WeatherA2uiChat } from "@weather/a2ui-client/src/chat";
import { LitElement, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import { MetricsCollector, byteLength } from "../metrics";
import type { Step } from "../scenarios";
import type { Pane, Theme } from "./types";

const RECORDED = import.meta.glob("../../../scenarios/recorded/*.json", {
  eager: true,
  import: "default",
}) as Record<string, unknown>;

const A2UI_KINDS = new Set(["createSurface", "updateComponents", "updateDataModel", "deleteSurface"]);
const DATA_KINDS = new Set(["updateComponents", "updateDataModel"]);

@customElement("a2ui-pane")
export class A2uiPane extends LitElement implements Pane {
  @property({ attribute: false }) config!: { a2uiUrl: string };
  readonly metrics = new MetricsCollector("a2ui");
  protected createRenderRoot() {
    return this;
  }

  private get chat(): WeatherA2uiChat {
    return this.querySelector("weather-a2ui-chat")!;
  }

  async connect(): Promise<void> {
    const chat = this.chat;
    chat.hooks = {
      onProtocol: (e) => {
        const a2ui = A2UI_KINDS.has(e.kind);
        if (a2ui) this.metrics.addUiBytes(byteLength(e.payload));
        this.metrics.record({
          at: e.at,
          direction: e.direction,
          channel: "network",
          kind: e.kind,
          payload: e.payload,
          bytes: e.bytes,
          roundTrip: e.direction === "out" && e.kind === "message/stream",
        });
        this.dispatchEvent(new CustomEvent("log"));
      },
      // Only paints that follow data received in this run count (a frame
      // scheduled by the previous run can fire after start()).
      onRendered: () => {
        if (!this.metrics.log.some((e) => e.direction === "in" && DATA_KINDS.has(e.kind))) return;
        this.metrics.markRendered();
        this.dispatchEvent(new CustomEvent("log")); // refresh the inspector
      },
      onText: () => {
        if (this.metrics.log.some((e) => e.direction === "in")) this.metrics.markRendered();
      },
      onTurnEnd: ({ metadata }) => {
        const usage = metadata?.usage as
          { llm_calls?: number; input_tokens?: number; output_tokens?: number } | undefined;
        if (usage)
          this.metrics.addLlmUsage(usage.llm_calls ?? 0, usage.input_tokens ?? 0, usage.output_tokens ?? 0);
      },
    };
    await chat.agent.ready();
  }

  async reset(): Promise<void> {
    this.chat.reset();
    await this.connect();
  }

  async runStep(step: Step, prompt: string, first: boolean): Promise<void> {
    if (step.kind === "click") return;
    if (first) this.chat.note(prompt);
    const scripted =
      step.kind === "tool"
        ? { tool: step.tool, args: step.args }
        : { compose: RECORDED[`../../../scenarios/${step.file}`] };
    if (step.kind === "compose" && !scripted.compose) throw new Error(`Missing recording ${step.file}`);
    await this.chat.ask(prompt, { scripted }, true);
  }

  async ask(prompt: string): Promise<void> {
    await this.chat.ask(prompt);
  }

  setTheme(theme: Theme): void {
    // The client owns the look: A2UI CSS variables follow the container's scheme.
    this.classList.toggle("a2ui-dark", theme === "dark");
    this.classList.toggle("a2ui-light", theme === "light");
  }

  render() {
    return html`<weather-a2ui-chat
      agent-url=${this.config.a2uiUrl}
      hide-input
      data-testid="transcript-a2ui"
    ></weather-a2ui-chat>`;
  }
}
