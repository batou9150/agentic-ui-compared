import { describe, expect, it } from "vitest";
import { MetricsCollector, byteLength, toCsv, type LogEntry } from "../src/metrics";

function clock() {
  let t = 0;
  return { now: () => t, advance: (ms: number) => (t += ms) };
}

const entry = (over: Partial<LogEntry>): LogEntry => ({
  at: 0,
  direction: "out",
  channel: "network",
  kind: "x",
  payload: {},
  bytes: 0,
  ...over,
});

describe("MetricsCollector", () => {
  it("sums network bytes, counts round trips and bridge messages", () => {
    const c = new MetricsCollector("mcp", clock().now);
    c.start();
    c.record(entry({ bytes: 100, roundTrip: true }));
    c.record(entry({ direction: "in", bytes: 900 }));
    c.record(entry({ channel: "bridge", bytes: 5000 }));
    c.record(entry({ bytes: 50, roundTrip: true }));
    c.record(entry({ channel: "bridge", kind: "ping" }));
    c.record(entry({ channel: "bridge", kind: "ping → result" }));
    c.addUiBytes(1234);
    const m = c.snapshot("S1", "scripted");
    expect(m).toMatchObject({ networkBytes: 1050, roundTrips: 2, bridgeMessages: 1, uiBytes: 1234 });
  });

  it("measures time to first render once, relative to start", () => {
    const k = clock();
    const c = new MetricsCollector("a2ui", k.now);
    k.advance(1000);
    c.start();
    k.advance(42.25);
    c.markRendered();
    k.advance(100);
    c.markRendered();
    c.markEnded();
    const m = c.snapshot("S1", "scripted");
    expect(m.firstRenderMs).toBe(42.3);
    expect(m.totalMs).toBe(142.3);
  });

  it("ignores marks before start and resets on start", () => {
    const c = new MetricsCollector("a2ui", clock().now);
    c.markRendered();
    c.addLlmUsage(1, 10, 2);
    c.start();
    c.addLlmUsage(2, 300, 20);
    expect(c.snapshot("S1", "live")).toMatchObject({ firstRenderMs: null, llmCalls: 2, inputTokens: 300 });
  });
});

describe("export", () => {
  it("writes CSV with a header and escapes values", () => {
    const c = new MetricsCollector("mcp", clock().now);
    c.start();
    const csv = toCsv([c.snapshot('S"1', "scripted")]);
    const [header, row] = csv.trim().split("\n");
    expect(header.split(",")[0]).toBe("scenario");
    expect(row.startsWith('"S""1",mcp,scripted')).toBe(true);
  });

  it("counts UTF-8 bytes", () => {
    expect(byteLength("°C")).toBe(3);
    expect(byteLength({ a: 1 })).toBe(7);
  });
});
