// <weather-a2ui-chat>: a minimal chat where agent surfaces render inline,
// with the official A2UI Lit renderer (<a2ui-surface>).
import "@a2ui/lit/v0_9";
import type { SurfaceModel } from "@a2ui/web_core/v0_9";
import { renderMarkdown } from "@a2ui/markdown-it";
import { injectBasicCatalogStyles, setMarkdownRenderer } from "@a2ui/web_core/v0_9/basic_catalog";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { A2uiAgentConnection, type ConnectionHooks, type TurnResult } from "./connection";

// Text components render Markdown; the official renderer sanitizes with DOMPurify.
setMarkdownRenderer(renderMarkdown);

type Item =
  | { kind: "user"; text: string }
  | { kind: "agent"; text: string }
  | { kind: "error"; text: string }
  | { kind: "surface"; surface: SurfaceModel };

@customElement("weather-a2ui-chat")
export class WeatherA2uiChat extends LitElement {
  @property({ attribute: "agent-url" }) agentUrl = "http://localhost:10002";
  @property({ attribute: false }) hooks: ConnectionHooks = {};
  @property({ type: Boolean, attribute: "hide-input" }) hideInput = false;
  @state() private items: Item[] = [];
  @state() private pending = false;
  private connection?: A2uiAgentConnection;

  // Light DOM, so the A2UI basic catalog styles and the page theme apply.
  protected createRenderRoot() {
    injectBasicCatalogStyles(document);
    return this;
  }

  get agent(): A2uiAgentConnection {
    this.connection ??= new A2uiAgentConnection(this.agentUrl, {
      ...this.hooks,
      onSurface: (surface) => {
        this.items = [...this.items, { kind: "surface", surface }];
        this.hooks.onSurface?.(surface);
      },
      onText: (text) => {
        this.items = [...this.items, { kind: "agent", text }];
        this.hooks.onText?.(text);
      },
      onError: (error) => {
        this.items = [...this.items, { kind: "error", text: error.message }];
        this.hooks.onError?.(error);
      },
    });
    return this.connection;
  }

  /** Send a prompt as if typed; `metadata.scripted` replays a tool without the LLM. */
  async ask(text: string, metadata?: Record<string, unknown>): Promise<TurnResult | undefined> {
    this.items = [...this.items, { kind: "user", text }];
    this.pending = true;
    try {
      return await this.agent.sendText(text, metadata);
    } catch {
      return undefined;
    } finally {
      this.pending = false;
    }
  }

  reset(): void {
    this.connection?.reset();
    this.connection = undefined;
    this.items = [];
  }

  private onSubmit(e: SubmitEvent): void {
    e.preventDefault();
    const input = (e.target as HTMLFormElement).elements.namedItem("prompt") as HTMLInputElement;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    void this.ask(text);
  }

  render() {
    return html`
      <div class="transcript" data-testid="transcript">
        ${this.items.map((item) => {
          switch (item.kind) {
            case "surface":
              return html`<div class="surface" data-testid="surface-${item.surface.id}">
                <a2ui-surface .surface=${item.surface}></a2ui-surface>
              </div>`;
            default:
              return html`<p class="msg ${item.kind}" data-testid="msg-${item.kind}">${item.text}</p>`;
          }
        })}
        ${this.pending ? html`<p class="msg pending" data-testid="pending">…</p>` : nothing}
      </div>
      ${
        this.hideInput
          ? nothing
          : html`<form @submit=${this.onSubmit}>
              <input
                name="prompt"
                placeholder="Ask about the weather…"
                data-testid="chat-input"
                autocomplete="off"
              />
              <button type="submit" data-testid="chat-send" ?disabled=${this.pending}>Send</button>
            </form>`
      }
    `;
  }

  static styles = css``;
}

export const chatStyles = `
weather-a2ui-chat { display: flex; flex-direction: column; gap: 8px; }
weather-a2ui-chat .transcript { display: flex; flex-direction: column; gap: 8px; }
weather-a2ui-chat .msg { margin: 0; padding: 6px 10px; border-radius: 8px; max-width: 90%; }
weather-a2ui-chat .msg.user { align-self: flex-end; background: var(--a2ui-color-secondary); }
weather-a2ui-chat .msg.agent { align-self: flex-start; white-space: pre-wrap; }
weather-a2ui-chat .msg.error { color: #c0392b; }
weather-a2ui-chat form { display: flex; gap: 6px; }
weather-a2ui-chat input { flex: 1; padding: 6px 8px; font: inherit; }
`;
