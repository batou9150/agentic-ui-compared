// Every scenario, Scripted mode, both panes: same inputs, assert what the user
// sees and what crossed the wire.
import { expect, test } from "@playwright/test";
import { SCENARIOS, SIDES, click, expectVisible, logKinds, openHarness, run } from "./harness";

for (const scenario of SCENARIOS) {
  test(`${scenario.id} ${scenario.title}`, async ({ page }) => {
    await openHarness(page, `scenario=${scenario.id}`);
    await run(page);
    for (const side of SIDES) {
      const steps = scenario.steps[side];
      for (const step of steps) {
        if (step.kind === "click") await click(page, side, step.label);
        await expectVisible(page, side, step.expect);
      }
      await expectVisible(page, side, ["Weather data by Open-Meteo.com"]);
    }
  });
}

test("S1 protocol: ui:// view vs A2UI messages", async ({ page }) => {
  await openHarness(page, "scenario=S1");
  await run(page);
  await expect
    .poll(() => logKinds(page, "mcp"))
    .toEqual(
      expect.arrayContaining([
        "resources/read",
        "tools/call",
        "ui/notifications/sandbox-resource-ready",
        "ui/initialize",
        "ui/notifications/tool-input",
        "ui/notifications/tool-result",
      ]),
    );
  await expect
    .poll(() => logKinds(page, "a2ui"))
    .toEqual(
      expect.arrayContaining(["message/stream", "createSurface", "updateComponents", "updateDataModel"]),
    );
});

test("S2 click reaches the server / the agent", async ({ page }) => {
  await openHarness(page, "scenario=S2");
  await run(page);
  await click(page, "mcp", "Illinois");
  await click(page, "a2ui", "Illinois");
  await expectVisible(page, "mcp", ["Springfield, Illinois, United States"]);
  await expectVisible(page, "a2ui", ["Springfield, Illinois, United States"]);
  const mcp = await logKinds(page, "mcp");
  // The view calls the tool through the host (bridge), the host calls the server.
  expect(mcp.filter((k) => k === "tools/call").length).toBeGreaterThanOrEqual(3);
  expect(mcp).toContain("ui/update-model-context");
  const a2ui = await logKinds(page, "a2ui");
  expect(a2ui).toContain("action");
  expect(a2ui.filter((k) => k === "message/stream")).toHaveLength(2);
});

test("S3 controls update the chart without a new chat message", async ({ page }) => {
  await openHarness(page, "scenario=S3");
  await run(page);
  for (const side of ["mcp", "a2ui"] as const) {
    await click(page, side, "16 days");
    await expectVisible(page, side, ["16-day forecast · °C"]);
  }
  for (const side of ["mcp", "a2ui"] as const) {
    const bubbles = page.getByTestId(`pane-${side}`).getByTestId("msg-user");
    await expect(bubbles).toHaveCount(1); // only the initial prompt
  }
  // A2UI: the second response only carries data, the layout is untouched.
  const kinds = await logKinds(page, "a2ui");
  const afterAction = kinds.slice(kinds.lastIndexOf("action"));
  expect(afterAction).toContain("updateDataModel");
  expect(afterAction).not.toContain("updateComponents");
});
