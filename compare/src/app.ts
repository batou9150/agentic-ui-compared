// The comparison harness: same scenario, same inputs, both implementations.
import { LitElement, html, nothing } from "lit";
import { customElement, query, state } from "lit/decorators.js";
import "./inspector";
import type { ProtocolInspector } from "./inspector";
import { toCsv, type Mode, type RunMetrics } from "./metrics";
import "./panes/a2ui-pane";
import "./panes/mcp-pane";
import type { Pane, Theme } from "./panes/types";
import { loadScenarios, type Scenario, type Side } from "./scenarios";

const SCENARIOS = loadScenarios(
  import.meta.glob("../../scenarios/*.yaml", { eager: true, query: "?raw", import: "default" }) as Record<
    string,
    string
  >,
);

interface Endpoints {
  mcpUrl: string;
  a2uiUrl: string;
}

interface Config {
  scripted: Endpoints;
  live: Endpoints;
  sandboxUrl: string;
  model: string;
}

const params = new URLSearchParams(location.search);

@customElement("compare-app")
export class CompareApp extends LitElement {
  @state() private config?: Config;
  @state() private scenario: Scenario = SCENARIOS[0];
  @state() private prompt = SCENARIOS[0].prompt;
  @state() private mode: Mode = params.get("mode") === "live" ? "live" : "scripted";
  @state() private theme: Theme = params.get("theme") === "dark" ? "dark" : "light";
  @state() private running = false;
  @state() private ready = false;
  @state() private error = "";
  @state() private results: RunMetrics[] = [];
  private current?: { scenario: string; mode: Mode };
  private readonly only = (params.get("side") as Side | null) ?? undefined;

  @query("mcp-pane") private mcp?: Pane;
  @query("a2ui-pane") private a2ui?: Pane;

  protected createRenderRoot() {
    return this;
  }

  private get panes(): Pane[] {
    return [this.mcp, this.a2ui].filter(
      (p): p is Pane => !!p && (!this.only || p.metrics.side === this.only),
    );
  }

  async connectedCallback(): Promise<void> {
    super.connectedCallback();
    document.documentElement.dataset.theme = this.theme;
    this.config = (await (await fetch("/api/config")).json()) as Config;
    await this.updateComplete;
    try {
      await Promise.all(this.panes.map((p) => p.connect()));
      for (const p of this.panes) p.setTheme(this.theme);
      this.ready = true;
    } catch (error) {
      this.error = `Cannot reach the backends (make compare starts them): ${(error as Error).message}`;
    }
    for (const p of this.panes) p.addEventListener("log", () => this.inspector(p)?.refresh());
    const id = params.get("scenario");
    if (id) this.pick(id);
  }

  private inspector(pane: Pane): ProtocolInspector | null {
    return this.querySelector(`protocol-inspector[side=${pane.metrics.side}]`);
  }

  private pick(id: string): void {
    this.scenario = SCENARIOS.find((s) => s.id === id) ?? this.scenario;
    this.prompt = this.scenario.prompt;
  }

  /** Close the current run: its metrics (including clicks) become a results row. */
  finishRun(): void {
    if (!this.current) return;
    const { scenario, mode } = this.current;
    this.results = [...this.results, ...this.panes.map((p) => p.metrics.snapshot(scenario, mode))];
    this.current = undefined;
  }

  async run(): Promise<void> {
    this.finishRun();
    this.running = true;
    await Promise.all(this.panes.map((p) => p.reset()));
    this.current = { scenario: this.scenario.id, mode: this.mode };
    await Promise.all(
      this.panes.map(async (pane) => {
        pane.metrics.start();
        if (this.mode === "live") {
          await pane.ask(this.prompt);
        } else {
          const steps = this.scenario.steps[pane.metrics.side];
          for (const [i, step] of steps.entries()) await pane.runStep(step, this.prompt, i === 0);
        }
        pane.metrics.markEnded();
        this.inspector(pane)?.refresh();
      }),
    );
    this.running = false;
  }

  async reset(): Promise<void> {
    this.finishRun();
    await Promise.all(this.panes.map((p) => p.reset()));
    for (const p of this.panes) p.metrics.start();
    this.requestUpdate();
  }

  /** Scripted and Live use different backend instances: reconnect both panes. */
  private async switchMode(mode: Mode): Promise<void> {
    this.finishRun();
    this.mode = mode;
    this.ready = false;
    await this.updateComplete;
    try {
      await Promise.all(this.panes.map((p) => p.reset()));
      this.ready = true;
      this.error = "";
    } catch (error) {
      this.error = `Cannot reach the ${mode} backends: ${(error as Error).message}`;
    }
  }

  private toggleTheme(): void {
    this.theme = this.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = this.theme;
    for (const p of this.panes) p.setTheme(this.theme);
  }

  private download(kind: "json" | "csv"): void {
    this.finishRun();
    const body = kind === "json" ? JSON.stringify(this.results, null, 2) : toCsv(this.results);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(
      new Blob([body], { type: kind === "json" ? "application/json" : "text/csv" }),
    );
    a.download = `compare-results.${kind}`;
    a.click();
  }

  private pendingClicks(): string[] {
    if (this.mode !== "scripted") return [];
    return this.scenario.steps.mcp.flatMap((s) => (s.kind === "click" ? [s.label] : []));
  }

  private renderPane(side: Side) {
    if (this.only && this.only !== side) return nothing;
    const pane =
      side === "mcp"
        ? html`<mcp-pane
            .config=${{ ...this.config![this.mode], sandboxUrl: this.config!.sandboxUrl }}
          ></mcp-pane>`
        : html`<a2ui-pane .config=${this.config![this.mode]}></a2ui-pane>`;
    const metrics = side === "mcp" ? this.mcp?.metrics : this.a2ui?.metrics;
    return html`<section class="pane" data-testid="pane-${side}">
      <h2>${side === "mcp" ? "MCP Apps" : "A2UI"}</h2>
      <div class="pane-body">${pane}</div>
      ${
        metrics
          ? html`<protocol-inspector
              side=${side}
              scenario=${this.scenario.id}
              mode=${this.mode}
              .metrics=${metrics}
            ></protocol-inspector>`
          : nothing
      }
    </section>`;
  }

  render() {
    if (!this.config) return html`<p>Loading…</p>`;
    const clicks = this.pendingClicks();
    return html`
      <header class="topbar">
        <select
          data-testid="scenario-select"
          .value=${this.scenario.id}
          @change=${(e: Event) => this.pick((e.target as HTMLSelectElement).value)}
        >
          ${SCENARIOS.map((s) => html`<option value=${s.id} ?selected=${s.id === this.scenario.id}>${s.id} ${s.title}</option>`)}
        </select>
        <input
          data-testid="prompt-input"
          .value=${this.prompt}
          ?readonly=${this.mode === "scripted"}
          @input=${(e: Event) => (this.prompt = (e.target as HTMLInputElement).value)}
        />
        <select
          data-testid="mode-select"
          .value=${this.mode}
          @change=${(e: Event) => this.switchMode((e.target as HTMLSelectElement).value as Mode)}
        >
          <option value="scripted">Scripted (no LLM, fixtures)</option>
          <option value="live">Live (${this.config.model})</option>
        </select>
        <button data-testid="run-both" ?disabled=${!this.ready || this.running} @click=${this.run}>
          ${this.only ? "Run" : "Run on both"}
        </button>
        <button data-testid="reset" ?disabled=${this.running} @click=${this.reset}>Reset</button>
        <button data-testid="theme-toggle" @click=${this.toggleTheme}>
          ${this.theme === "light" ? "Dark" : "Light"} theme
        </button>
      </header>
      ${this.error ? html`<p class="banner error" data-testid="error">${this.error}</p>` : nothing}
      ${
        clicks.length
          ? html`<p class="banner" data-testid="pending-actions">
              User actions in this scenario (click in each pane): ${clicks.map((c) => html`<kbd>${c}</kbd>`)}
            </p>`
          : nothing
      }
      <main class="panes ${this.only ? "solo" : ""}" data-ready=${this.ready} data-running=${this.running}>
        ${this.renderPane("mcp")} ${this.renderPane("a2ui")}
      </main>
      <section class="results">
        <h2>Results</h2>
        <button data-testid="finish-run" @click=${() => this.finishRun()}>Record current run</button>
        <button data-testid="export-json" @click=${() => this.download("json")}>Export JSON</button>
        <button data-testid="export-csv" @click=${() => this.download("csv")}>Export CSV</button>
        <table data-testid="results-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Side</th>
              <th>Mode</th>
              <th>Network</th>
              <th>UI payload</th>
              <th>Round trips</th>
              <th>First render</th>
              <th>LLM calls</th>
              <th>Tokens in/out</th>
            </tr>
          </thead>
          <tbody>
            ${this.results.map(
              (r) =>
                html`<tr>
                  <td>${r.scenario}</td>
                  <td>${r.side}</td>
                  <td>${r.mode}</td>
                  <td>${r.networkBytes}</td>
                  <td>${r.uiBytes}</td>
                  <td>${r.roundTrips}</td>
                  <td>${r.firstRenderMs ?? "–"}</td>
                  <td>${r.llmCalls}</td>
                  <td>${r.inputTokens}/${r.outputTokens}</td>
                </tr>`,
            )}
          </tbody>
        </table>
      </section>
      <footer class="attribution">
        Weather data by <a href="https://open-meteo.com/">Open-Meteo.com</a> (CC BY 4.0)
      </footer>
    `;
  }
}

declare global {
  interface Window {
    compare?: CompareApp;
  }
}
