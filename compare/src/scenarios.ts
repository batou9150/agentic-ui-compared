// Scenario loader: scenarios/*.yaml -> typed, validated scenarios.
// Used by the harness (browser) and by the Playwright e2e tests (Node).
import { parse } from "yaml";

export type Side = "mcp" | "a2ui";

export type Step =
  | { kind: "tool"; tool: string; args: Record<string, unknown>; expect: string[] }
  | { kind: "click"; label: string; expect: string[] }
  | { kind: "compose"; file: string; expect: string[] };

export interface Scenario {
  id: string;
  title: string;
  prompt: string;
  steps: Record<Side, Step[]>;
}

export class ScenarioError extends Error {}

function toStep(raw: unknown, where: string): Step {
  if (typeof raw !== "object" || raw === null) throw new ScenarioError(`${where}: a step must be a mapping`);
  const r = raw as Record<string, unknown>;
  const expect = r.expect === undefined ? [] : r.expect;
  if (!Array.isArray(expect) || !expect.every((e) => typeof e === "string")) {
    throw new ScenarioError(`${where}: expect must be a list of strings`);
  }
  if (typeof r.tool === "string") {
    const args = r.args ?? {};
    if (typeof args !== "object" || args === null || Array.isArray(args)) {
      throw new ScenarioError(`${where}: args must be a mapping`);
    }
    return { kind: "tool", tool: r.tool, args: args as Record<string, unknown>, expect };
  }
  if (typeof r.click === "string") return { kind: "click", label: r.click, expect };
  if (typeof r.compose === "string") return { kind: "compose", file: r.compose, expect };
  throw new ScenarioError(`${where}: a step needs one of tool, click or compose`);
}

function toSteps(raw: unknown, where: string): Step[] {
  if (!Array.isArray(raw) || raw.length === 0)
    throw new ScenarioError(`${where}: steps must be a non-empty list`);
  return raw.map((s, i) => toStep(s, `${where}[${i}]`));
}

export function parseScenario(text: string, source = "scenario"): Scenario {
  const raw = parse(text) as Record<string, unknown> | null;
  if (!raw || typeof raw !== "object") throw new ScenarioError(`${source}: empty document`);
  for (const key of ["id", "title", "prompt"]) {
    if (typeof raw[key] !== "string" || !raw[key]) throw new ScenarioError(`${source}: missing ${key}`);
  }
  const steps = raw.steps;
  let perSide: Record<Side, Step[]>;
  if (Array.isArray(steps)) {
    const shared = toSteps(steps, `${source}.steps`);
    perSide = { mcp: shared, a2ui: shared };
  } else if (steps && typeof steps === "object") {
    const s = steps as Record<string, unknown>;
    perSide = { mcp: toSteps(s.mcp, `${source}.steps.mcp`), a2ui: toSteps(s.a2ui, `${source}.steps.a2ui`) };
  } else {
    throw new ScenarioError(`${source}: missing steps`);
  }
  for (const step of perSide.mcp) {
    if (step.kind === "compose") throw new ScenarioError(`${source}: compose steps are A2UI only`);
  }
  return { id: raw.id as string, title: raw.title as string, prompt: raw.prompt as string, steps: perSide };
}

export function loadScenarios(files: Record<string, string>): Scenario[] {
  const scenarios = Object.entries(files).map(([path, text]) => parseScenario(text, path));
  const ids = new Set<string>();
  for (const s of scenarios) {
    if (ids.has(s.id)) throw new ScenarioError(`duplicate scenario id ${s.id}`);
    ids.add(s.id);
  }
  return scenarios.sort((a, b) => a.id.localeCompare(b.id, "en", { numeric: true }));
}
