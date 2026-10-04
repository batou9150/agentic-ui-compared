import base from "../playwright.config";
import { defineConfig } from "@playwright/test";

export default defineConfig({
  ...base,
  testDir: ".",
  retries: 0,
  reporter: "list",
  outputDir: "../test-results/record",
  use: {
    ...base.use,
    trace: "off",
    viewport: { width: 1440, height: 1000 },
    video: { mode: "on", size: { width: 1440, height: 1000 } },
  },
});
