import base from "../playwright.config";
import { defineConfig } from "@playwright/test";

export default defineConfig({
  ...base,
  testDir: ".",
  retries: 0,
  reporter: "list",
  use: { ...base.use, trace: "off" },
  webServer: {
    ...base.webServer!,
    // Live measurements need the Live backends too.
    command: process.env.MEASURE_MODE === "live" ? "make compare" : "make compare-scripted",
  },
});
