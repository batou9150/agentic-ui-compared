// Records the side-by-side videos used for the GIFs (scripts/record_gifs.sh).
// Scripted mode, both panes, inspectors open, pauses so a reader can follow.
import { test } from "@playwright/test";
import { SCENARIOS, SIDES, click, expectVisible, openHarness, run } from "../e2e/harness";

const ONLY = (process.env.RECORD_SCENARIOS ?? "S1,S2,S3,S4,S5").split(",");
const THEME = process.env.RECORD_THEME ?? "light";

for (const scenario of SCENARIOS.filter((s) => ONLY.includes(s.id))) {
  test(`record ${scenario.id}`, async ({ page }) => {
    await openHarness(page, `scenario=${scenario.id}&theme=${THEME}`);
    await page.waitForTimeout(800);
    await run(page);
    await page.waitForTimeout(1500);
    const clicks = Math.max(...SIDES.map((s) => scenario.steps[s].filter((x) => x.kind === "click").length));
    for (let i = 0; i < clicks; i++) {
      for (const side of SIDES) {
        const step = scenario.steps[side].filter((x) => x.kind === "click")[i];
        if (!step || step.kind !== "click") continue;
        await click(page, side, step.label);
        await expectVisible(page, side, step.expect);
        await page.waitForTimeout(900);
      }
    }
    if (scenario.id === "S4") await page.waitForTimeout(2500); // clocks ticking
    await page.waitForTimeout(1500);
  });
}
