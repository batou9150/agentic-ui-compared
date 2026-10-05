// Drives the harness N times per scenario (Scripted by default) and saves the
// harness's own JSON export. Run through scripts/measure.py, not in CI.
import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SCENARIOS, SIDES, click, expectVisible, openHarness, run } from "../e2e/harness";

const RUNS = Number(process.env.MEASURE_RUNS ?? 10);
const MODE = process.env.MEASURE_MODE === "live" ? "live" : "scripted";
const OUT = process.env.MEASURE_OUT ?? join(import.meta.dirname, "../../measurements/raw");

test.setTimeout(30 * 60_000);

test(`measure ${MODE}, ${RUNS} runs per scenario`, async ({ page }) => {
  await openHarness(page, `mode=${MODE}`, { fakeClock: false });
  for (const scenario of SCENARIOS) {
    await page.getByTestId("scenario-select").selectOption(scenario.id);
    // One warm-up run (JIT, caches, connections), then the measured runs.
    for (let i = 0; i <= RUNS; i++) {
      await run(page, { timeout: MODE === "live" ? 120_000 : 8_000 }); // Live waits for Gemini
      for (const side of SIDES) {
        for (const step of scenario.steps[side]) {
          if (MODE === "live" && step.kind !== "click") continue;
          if (step.kind === "click") await click(page, side, step.label);
          if (MODE === "scripted") await expectVisible(page, side, step.expect);
        }
      }
      await page.waitForTimeout(MODE === "live" ? 1000 : 200); // let trailing notifications land
      await page.getByTestId("finish-run").click(); // run 0 is a warm-up, dropped by measure.py
      await expect(page.locator("main.panes")).toHaveAttribute("data-running", "false");
    }
  }
  const download = page.waitForEvent("download");
  await page.getByTestId("export-json").click();
  const rows = JSON.parse(readFileSync(await (await download).path(), "utf8"));
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, `runs-${MODE}.json`), JSON.stringify(rows, null, 2) + "\n");
  expect(rows).toHaveLength(SCENARIOS.length * (RUNS + 1) * SIDES.length);
});
