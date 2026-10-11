import { defineConfig, devices } from "@playwright/test";

// End-to-end checks against a running app (start it first with `python3 run.py`).
// The demo-account tests run in order because they share one account; the reset at the end leaves it fresh.
export default defineConfig({
  testDir: "tests",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.FINPILOT_URL ?? "http://localhost:8000",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /global\.setup\.ts/ },
    { name: "new-user", testMatch: /new-user\.spec\.ts/, dependencies: ["setup"], use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    {
      name: "demo",
      testMatch: /demo\.spec\.ts/,
      dependencies: ["setup", "new-user"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, storageState: ".auth/demo.json" },
    },
  ],
});
