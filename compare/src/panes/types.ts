import type { MetricsCollector } from "../metrics";
import type { Step } from "../scenarios";

export type Theme = "light" | "dark";

/** What the harness needs from each side. */
export interface Pane extends HTMLElement {
  readonly metrics: MetricsCollector;
  connect(): Promise<void>;
  reset(): Promise<void>;
  /** Scripted mode: replay one step (no LLM). Clicks are left to the user / Playwright. */
  runStep(step: Step, prompt: string, first: boolean): Promise<void>;
  /** Live mode: the prompt goes to the side's LLM. */
  ask(prompt: string): Promise<void>;
  setTheme(theme: Theme): void;
}
