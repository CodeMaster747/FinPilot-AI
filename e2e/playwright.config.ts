import { defineConfig, devices } from "@playwright/test";

// End-to-end checks against a running FinPilot server. Start one first, ideally on a throwaway data folder:
//   FINPILOT_DATA_DIR=/tmp/finpilot-e2e FINPILOT_PORT=8123 python3 run.py --no-browser
//   FINPILOT_URL=http://localhost:8123 npx playwright test
// The new-user journey creates its own account and deletes it at the end. The demo tests change the demo account
// and reset it as their last step.
export default defineConfig({
  testDir: "tests",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.FINPILOT_URL ?? "http://localhost:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /global\.setup\.ts/ },
    { name: "new-user", testMatch: /new-user\.spec\.ts/, dependencies: ["setup"], use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    // A phone-sized, touch-screen browser: the same UI the Android app shows.
    { name: "mobile", testMatch: /mobile\.spec\.ts/, dependencies: ["setup"], use: { ...devices["Pixel 7"], storageState: ".auth/demo.json" } },
    {
      name: "demo",
      testMatch: /demo\.spec\.ts/,
      dependencies: ["setup", "new-user", "mobile"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, storageState: ".auth/demo.json" },
    },
  ],
});
