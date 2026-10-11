import { expect, test as setup } from "@playwright/test";

// Wait for the first-run work (demo data, analytics, crawl) to finish, then sign in to the demo once.
setup("demo is ready and signed in", async ({ page, request }) => {
  setup.setTimeout(300_000);
  await expect.poll(async () => {
    const res = await request.get("/api/v1/system/status");
    if (!res.ok()) return false;
    const s = await res.json();
    return s.demo_ready && s.active_jobs.length === 0;
  }, { timeout: 280_000, intervals: [2_000] }).toBe(true);
  await page.goto("/login/");
  await page.getByRole("button", { name: "Try the demo" }).click();
  await page.waitForURL("**/dashboard/");
  // The demo flow mutates shared data. Rebuild it before each suite so repeated
  // runs start with an unlinked receipt and the same seeded transactions.
  await page.goto("/settings/");
  await page.getByRole("button", { name: "Reset the demo" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reset" }).click();
  await page.waitForURL("**/login/");
  await expect(page.getByRole("button", { name: "Try the demo" })).toBeEnabled({ timeout: 240_000 });
  await page.getByRole("button", { name: "Try the demo" }).click();
  await page.waitForURL("**/dashboard/");
  await page.context().storageState({ path: ".auth/demo.json" });
});
