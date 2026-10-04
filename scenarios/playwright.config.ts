import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const REPO = fileURLToPath(new URL("..", import.meta.url));

const CI = !!process.env.CI;

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false, // one harness, shared backends
  workers: 1,
  retries: CI ? 1 : 0,
  reporter: CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: "http://localhost:8080",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    viewport: { width: 1400, height: 1000 },
  },
  webServer: {
    command: "make compare-scripted",
    cwd: REPO,
    url: "http://localhost:8080/api/config",
    reuseExistingServer: !CI,
    timeout: 120_000,
    stdout: "pipe",
  },
});
