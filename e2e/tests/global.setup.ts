import { expect, test as setup } from "@playwright/test";

// Wait for the first-run work (building the demo account, training the models) to finish, then sign in to the demo once.
setup("the demo account is ready and signed in", async ({ page, request }) => {
  setup.setTimeout(300_000);
  await expect.poll(async () => {
    const res = await request.get("/api/v1/system/status");
    return res.ok() && (await res.json()).demo_ready;
  }, { timeout: 280_000, intervals: [2_000] }).toBe(true);
  await page.goto("/login/");
  await page.getByRole("button", { name: "Explore the demo account (sample data)" }).click();
  await page.waitForURL("**/dashboard/");
  await page.context().storageState({ path: ".auth/demo.json" });
});
