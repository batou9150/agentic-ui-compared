import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ScenarioError, loadScenarios, parseScenario } from "../src/scenarios";

const DIR = join(import.meta.dirname, "../../scenarios");
const files = Object.fromEntries(
  readdirSync(DIR)
    .filter((f) => f.endsWith(".yaml"))
    .map((f) => [f, readFileSync(join(DIR, f), "utf8")]),
);

describe("repository scenarios", () => {
  const scenarios = loadScenarios(files);

  it("loads S1 to S5 in order", () => {
    expect(scenarios.map((s) => s.id)).toEqual(["S1", "S2", "S3", "S4", "S5"]);
  });

  it("shares steps between sides unless split", () => {
    const s2 = scenarios[1];
    expect(s2.steps.mcp).toBe(s2.steps.a2ui);
    expect(s2.steps.mcp.map((s) => s.kind)).toEqual(["tool", "click"]);
    const s5 = scenarios[4];
    expect(s5.steps.mcp.map((s) => s.kind)).toEqual(["tool", "tool"]);
    expect(s5.steps.a2ui.at(-1)).toMatchObject({ kind: "compose", file: "recorded/S5-a2ui-compose.json" });
  });

  it("keeps tool arguments", () => {
    expect(scenarios[3].steps.mcp[0]).toMatchObject({
      kind: "tool",
      tool: "get_world_clock",
      args: { cities: ["Paris", "Tokyo", "New York"] },
    });
  });
});

describe("validation", () => {
  const base = "id: X\ntitle: t\nprompt: p\n";

  it.each([
    ["missing steps", base],
    ["empty steps", base + "steps: []"],
    ["unknown step", base + "steps:\n  - wait: 3"],
    ["bad expect", base + "steps:\n  - tool: a\n    expect: 3"],
    ["bad args", base + "steps:\n  - tool: a\n    args: [1]"],
    ["compose on mcp", base + "steps:\n  mcp:\n    - compose: f.json\n  a2ui:\n    - tool: a"],
    ["missing id", "title: t\nprompt: p\nsteps:\n  - tool: a"],
  ])("rejects %s", (_name, text) => {
    expect(() => parseScenario(text)).toThrow(ScenarioError);
  });

  it("rejects duplicate ids", () => {
    const one = base + "steps:\n  - tool: a";
    expect(() => loadScenarios({ "a.yaml": one, "b.yaml": one })).toThrow(/duplicate/);
  });
});
