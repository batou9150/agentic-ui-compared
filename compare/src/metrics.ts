// Per-run metrics, computed from the protocol log of one pane.
export type Mode = "scripted" | "live";

export interface LogEntry {
  at: number; // ms, performance.now()
  direction: "out" | "in" | "local";
  channel: "network" | "bridge"; // network: HTTP to the backend; bridge: host <-> view postMessage
  kind: string;
  payload: unknown;
  bytes: number;
  roundTrip?: boolean; // true on the request that starts an HTTP round trip
}

export interface RunMetrics {
  scenario: string;
  side: "mcp" | "a2ui";
  mode: Mode;
  networkBytes: number;
  uiBytes: number; // bytes that describe the UI: ui:// HTML + view data, or A2UI messages
  bridgeMessages: number;
  roundTrips: number;
  firstRenderMs: number | null;
  totalMs: number | null;
  llmCalls: number;
  inputTokens: number;
  outputTokens: number;
}

export class MetricsCollector {
  private entries: LogEntry[] = [];
  private startedAt: number | null = null;
  private firstRenderAt: number | null = null;
  private endedAt: number | null = null;
  private llm = { calls: 0, input: 0, output: 0 };
  private uiBytes = 0;

  constructor(
    readonly side: "mcp" | "a2ui",
    private readonly now: () => number = () => performance.now(),
  ) {}

  start(): void {
    this.entries = [];
    this.startedAt = this.now();
    this.firstRenderAt = this.endedAt = null;
    this.llm = { calls: 0, input: 0, output: 0 };
    this.uiBytes = 0;
  }

  record(entry: LogEntry): void {
    this.entries.push(entry);
  }

  /** Bytes that carry the UI itself (counted by each side's adapter). */
  addUiBytes(bytes: number): void {
    this.uiBytes += bytes;
  }

  /** First time the user can see the requested information. */
  markRendered(): void {
    if (this.startedAt !== null && this.firstRenderAt === null) this.firstRenderAt = this.now();
  }

  markEnded(): void {
    if (this.startedAt !== null) this.endedAt = this.now();
  }

  addLlmUsage(calls: number, input: number, output: number): void {
    this.llm.calls += calls;
    this.llm.input += input;
    this.llm.output += output;
  }

  get log(): readonly LogEntry[] {
    return this.entries;
  }

  snapshot(scenario: string, mode: Mode): RunMetrics {
    const network = this.entries.filter((e) => e.channel === "network");
    const elapsed = (t: number | null) =>
      t === null || this.startedAt === null ? null : Math.round((t - this.startedAt) * 10) / 10;
    return {
      scenario,
      side: this.side,
      mode,
      networkBytes: network.reduce((sum, e) => sum + e.bytes, 0),
      uiBytes: this.uiBytes,
      bridgeMessages: this.entries.filter((e) => e.channel === "bridge").length,
      roundTrips: network.filter((e) => e.roundTrip).length,
      firstRenderMs: elapsed(this.firstRenderAt),
      totalMs: elapsed(this.endedAt),
      llmCalls: this.llm.calls,
      inputTokens: this.llm.input,
      outputTokens: this.llm.output,
    };
  }
}

export const METRIC_COLUMNS: (keyof RunMetrics)[] = [
  "scenario",
  "side",
  "mode",
  "networkBytes",
  "uiBytes",
  "bridgeMessages",
  "roundTrips",
  "firstRenderMs",
  "totalMs",
  "llmCalls",
  "inputTokens",
  "outputTokens",
];

export function toCsv(rows: RunMetrics[]): string {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return (
    [METRIC_COLUMNS.join(","), ...rows.map((r) => METRIC_COLUMNS.map((c) => escape(r[c])).join(","))].join(
      "\n",
    ) + "\n"
  );
}

export const byteLength = (value: unknown): number =>
  new TextEncoder().encode(typeof value === "string" ? value : (JSON.stringify(value) ?? "")).length;
