// The A2UI pane over AG-UI (?a2ui=agui), Scripted mode: same agent, renderer
// and catalog as over A2A, through the harness relay and @ag-ui/a2ui-middleware.
// A click is a turn of the agent (its replay model in Scripted mode).
import { expect, test } from "@playwright/test";
import { SCENARIOS, click, expectVisible, logKinds, openHarness, run } from "./harness";

const AGUI = "side=a2ui&a2ui=agui";

for (const scenario of SCENARIOS) {
  test(`AG-UI ${scenario.id} ${scenario.title}`, async ({ page }) => {
    await openHarness(page, `${AGUI}&scenario=${scenario.id}`);
    await expect(page.getByTestId("pane-title-a2ui")).toHaveText("A2UI over AG-UI");
    await run(page);
    for (const step of scenario.steps.a2ui) {
      if (step.kind === "click") await click(page, "a2ui", step.label);
      await expectVisible(page, "a2ui", step.expect);
    }
    await expectVisible(page, "a2ui", ["Weather data by Open-Meteo.com"]);
  });
}

test("AG-UI S1 protocol: runs, activity snapshots, A2UI messages", async ({ page }) => {
  await openHarness(page, `${AGUI}&scenario=S1`);
  await run(page);
  await expect
    .poll(() => logKinds(page, "a2ui"))
    .toEqual(
      expect.arrayContaining([
        "run",
        "agui:RUN_STARTED",
        "agui:TOOL_CALL_RESULT",
        "agui:ACTIVITY_SNAPSHOT",
        "createSurface",
        "updateComponents",
        "updateDataModel",
        "agui:CUSTOM",
        "agui:RUN_FINISHED",
      ]),
    );
});

test("AG-UI S2 click is an agent turn that redraws the picker in place", async ({ page }) => {
  await openHarness(page, `${AGUI}&scenario=S2`);
  await run(page);
  await click(page, "a2ui", "Illinois");
  await expectVisible(page, "a2ui", ["Springfield, Illinois, United States"]);
  const kinds = await logKinds(page, "a2ui");
  expect(kinds).toContain("action");
  expect(kinds.filter((k) => k === "run")).toHaveLength(2);
  const afterAction = kinds.slice(kinds.lastIndexOf("action"));
  expect(afterAction).toContain("agui:TOOL_CALL_START"); // the agent called a tool
  expect(afterAction).not.toContain("createSurface"); // same surface, redrawn
});
