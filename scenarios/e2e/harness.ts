// Helpers to drive the comparison harness from Playwright.
import { expect, type Frame, type Page } from "@playwright/test";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { loadScenarios, type Scenario, type Side } from "../../compare/src/scenarios";

const DIR = join(import.meta.dirname, "..");

export const SCENARIOS: Scenario[] = loadScenarios(
  Object.fromEntries(
    readdirSync(DIR)
      .filter((f) => f.endsWith(".yaml"))
      .map((f) => [f, readFileSync(join(DIR, f), "utf8")]),
  ),
);

export const SIDES: Side[] = ["mcp", "a2ui"];

// Scripted backends freeze "now" at this instant (scripts/compare.sh).
export const FROZEN = new Date("2026-10-04T12:00:00Z");

export async function openHarness(page: Page, query = ""): Promise<void> {
  await page.clock.install({ time: FROZEN });
  await page.clock.resume(); // time flows from the frozen instant: clocks still tick
  await page.goto(`/?${query}`);
  await expect(page.locator("main.panes")).toHaveAttribute("data-ready", "true", { timeout: 40_000 });
}

export async function run(page: Page): Promise<void> {
  await page.getByTestId("run-both").click();
  await expect(page.locator("main.panes")).toHaveAttribute("data-running", "false");
}

/** MCP Apps views: the inner (srcdoc) frames of the sandbox proxies. */
export function mcpViews(page: Page): Frame[] {
  return page.frames().filter((f) => f.url() === "about:srcdoc");
}

/** Everything a user can read on one side: transcript text + view contents. */
export async function visibleText(page: Page, side: Side): Promise<string> {
  // A2UI surfaces render inside shadow roots, which innerText does not enter.
  const pane = await page
    .getByTestId(`pane-${side}`)
    .locator(".pane-body")
    .evaluate((root) => {
      const walk = (node: Node): string => {
        if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
        const el = node as Element;
        const kids = [...(el.shadowRoot?.childNodes ?? []), ...node.childNodes];
        const text = kids.map(walk).join("");
        return el.tagName && /^(P|DIV|H\d|LI|SECTION|ARTICLE)$/.test(el.tagName) ? `${text}\n` : text;
      };
      return walk(root);
    });
  if (side === "a2ui") return pane;
  const views = await Promise.all(
    mcpViews(page).map((f) =>
      f
        .locator("body")
        .innerText()
        .catch(() => ""),
    ),
  );
  return [pane, ...views].join("\n");
}

export async function expectVisible(page: Page, side: Side, texts: string[]): Promise<void> {
  for (const text of texts) {
    await expect.poll(() => visibleText(page, side), { message: `${side}: "${text}"` }).toContain(text);
  }
}

/** Click a button by its label, inside the MCP views or the A2UI surfaces. */
export async function click(page: Page, side: Side, label: string): Promise<void> {
  if (side === "a2ui") {
    await page.getByTestId("pane-a2ui").getByRole("button", { name: label }).last().click();
    return;
  }
  await expect
    .poll(
      async () => {
        for (const frame of mcpViews(page).reverse()) {
          const button = frame.getByRole("button", { name: label });
          if ((await button.count()) > 0) {
            await button.last().click();
            return true;
          }
        }
        return false;
      },
      { message: `mcp: button "${label}"` },
    )
    .toBe(true);
}

export async function logKinds(page: Page, side: Side): Promise<string[]> {
  return page
    .getByTestId(`log-${side}`)
    .locator("li")
    .evaluateAll((items) => items.map((i) => i.getAttribute("data-kind") ?? ""));
}

export async function metric(page: Page, side: Side, name: string): Promise<string> {
  return page.getByTestId(`metric-${side}-${name}`).innerText();
}
