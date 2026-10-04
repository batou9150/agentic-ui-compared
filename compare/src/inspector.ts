// Collapsible inspector under each pane: protocol log (filter, copy) + metrics.
import { LitElement, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { LogEntry, MetricsCollector, Mode } from "./metrics";

const fmtBytes = (n: number) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);

@customElement("protocol-inspector")
export class ProtocolInspector extends LitElement {
  @property({ attribute: false }) metrics!: MetricsCollector;
  @property() side = "";
  @property() scenario = "";
  @property() mode: Mode = "scripted";
  @state() private filter = "all";
  @state() private version = 0;

  protected createRenderRoot() {
    return this;
  }

  refresh(): void {
    this.version++;
  }

  private visible(): readonly LogEntry[] {
    const log = this.metrics.log;
    if (this.filter === "all") return log;
    if (this.filter === "network" || this.filter === "bridge")
      return log.filter((e) => e.channel === this.filter);
    return log.filter((e) => e.kind === this.filter);
  }

  private async copy(): Promise<void> {
    await navigator.clipboard.writeText(JSON.stringify(this.visible(), null, 2));
  }

  render() {
    const log = this.metrics.log;
    const start = log[0]?.at ?? 0;
    const kinds = [...new Set(log.map((e) => e.kind))].sort();
    const m = this.metrics.snapshot(this.scenario, this.mode);
    const s = this.side;
    return html`<details class="inspector" data-testid="inspector-${s}" open>
      <summary>Inspector</summary>
      <dl class="metrics" data-testid="metrics-${s}">
        <dt>Network</dt>
        <dd data-testid="metric-${s}-networkBytes">${fmtBytes(m.networkBytes)}</dd>
        <dt>UI payload</dt>
        <dd data-testid="metric-${s}-uiBytes">${fmtBytes(m.uiBytes)}</dd>
        <dt>Round trips</dt>
        <dd data-testid="metric-${s}-roundTrips">${m.roundTrips}</dd>
        <dt>First render</dt>
        <dd data-testid="metric-${s}-firstRenderMs">${m.firstRenderMs ?? "–"} ms</dd>
        <dt>Bridge msgs</dt>
        <dd data-testid="metric-${s}-bridgeMessages">${m.bridgeMessages}</dd>
        <dt>LLM</dt>
        <dd data-testid="metric-${s}-llm">${m.llmCalls} calls, ${m.inputTokens}+${m.outputTokens} tok</dd>
      </dl>
      <div class="log-tools">
        <select
          data-testid="log-filter-${s}"
          @change=${(e: Event) => (this.filter = (e.target as HTMLSelectElement).value)}
        >
          <option value="all">all (${log.length})</option>
          <option value="network">network</option>
          ${s === "mcp" ? html`<option value="bridge">host ↔ view</option>` : nothing}
          ${kinds.map((k) => html`<option value=${k}>${k}</option>`)}
        </select>
        <button data-testid="log-copy-${s}" @click=${this.copy}>Copy as JSON</button>
      </div>
      <ol class="log" data-testid="log-${s}" data-version=${this.version}>
        ${this.visible().map(
          (e) =>
            html`<li class="entry ${e.channel} ${e.direction}" data-kind=${e.kind}>
              <details>
                <summary>
                  <span class="t">+${(e.at - start).toFixed(0)}ms</span>
                  <span class="dir">${e.direction === "out" ? "→" : e.direction === "in" ? "←" : "↔"}</span>
                  <span class="kind">${e.kind}</span>
                  <span class="bytes">${e.bytes ? fmtBytes(e.bytes) : ""}</span>
                </summary>
                <pre>${JSON.stringify(e.payload, null, 2)}</pre>
              </details>
            </li>`,
        )}
      </ol>
    </details>`;
  }
}
