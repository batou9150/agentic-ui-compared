// The harness itself: clocks, theming, results, export, solo mode.
import { expect, test } from "@playwright/test";
import { expectVisible, logKinds, metric, mcpViews, openHarness, run } from "./harness";

test("S4 clocks tick client-side from the frozen time, no round trip per second", async ({ page }) => {
  await openHarness(page, "scenario=S4");
  await run(page);
  const expected = {
    Paris: /^\s*14:0\d:\d\d\s*$/,
    Tokyo: /^\s*21:0\d:\d\d\s*$/,
    "New York": /^\s*08:0\d:\d\d\s*$/,
  };
  const a2uiClocks = page.getByTestId("pane-a2ui").getByTestId("clock");
  await expect(a2uiClocks).toHaveCount(3);
  const mcpClocks = () => mcpViews(page)[0].getByTestId("clock");
  await expect(mcpClocks()).toHaveCount(3);
  for (const [i, pattern] of Object.values(expected).entries()) {
    await expect(a2uiClocks.nth(i)).toHaveText(pattern);
    await expect(mcpClocks().nth(i)).toHaveText(pattern);
  }
  const trips = {
    mcp: await metric(page, "mcp", "roundTrips"),
    a2ui: await metric(page, "a2ui", "roundTrips"),
  };
  const before = await a2uiClocks.first().innerText();
  await page.clock.runFor(3000);
  await expect(a2uiClocks.first()).not.toHaveText(before);
  await expect(mcpClocks().first()).not.toHaveText(before);
  expect(await metric(page, "mcp", "roundTrips")).toBe(trips.mcp);
  expect(await metric(page, "a2ui", "roundTrips")).toBe(trips.a2ui);
});

test("theme: the host restyles MCP views, the client restyles A2UI surfaces", async ({ page }) => {
  await openHarness(page, "scenario=S1");
  await run(page);
  await expectVisible(page, "mcp", ["Feels like"]);
  const viewBg = () =>
    mcpViews(page)[0]
      .locator("body")
      .evaluate((b) => getComputedStyle(b).backgroundColor);
  const light = await viewBg();
  await page.getByTestId("theme-toggle").click();
  await expect.poll(viewBg).not.toBe(light);
  expect(await logKinds(page, "mcp")).toContain("ui/notifications/host-context-changed");
  await expect(page.locator("a2ui-pane")).toHaveClass(/a2ui-dark/);
});

test("results table accumulates runs and exports CSV", async ({ page }) => {
  await openHarness(page, "scenario=S1");
  await run(page);
  await page.getByTestId("finish-run").click();
  await expect(page.getByTestId("results-table").locator("tbody tr")).toHaveCount(2);
  const download = page.waitForEvent("download");
  await page.getByTestId("export-csv").click();
  const file = await (await download).path();
  const { readFileSync } = await import("node:fs");
  const csv = readFileSync(file, "utf8").trim().split("\n");
  expect(csv[0]).toContain("scenario,side,mode,networkBytes");
  expect(csv.slice(1).map((r) => r.split(",").slice(0, 3).join(","))).toEqual([
    "S1,mcp,scripted",
    "S1,a2ui,scripted",
  ]);
});

test("solo mode shows one side full width", async ({ page }) => {
  await openHarness(page, "scenario=S1&side=a2ui");
  await expect(page.getByTestId("pane-mcp")).toHaveCount(0);
  await run(page);
  await expectVisible(page, "a2ui", ["Paris, Île-de-France Region, France"]);
});
