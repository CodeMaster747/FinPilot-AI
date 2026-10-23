import { expect, test } from "@playwright/test";

// The phone layout: what the Android app shows (the app bundles this same UI). Pixel 7 size, touch screen.
const PAGES = ["dashboard", "transactions", "connections", "review", "scan", "forecast", "subscriptions", "wishlist", "insights", "budgets", "tax", "settings"];

test("bottom tabs and the More menu reach every section", async ({ page }) => {
  await page.goto("/dashboard/");
  const tabs = page.getByRole("navigation", { name: "Main" });
  await tabs.getByRole("link", { name: "Transactions" }).click();
  await page.waitForURL("**/transactions/");
  await tabs.getByRole("link", { name: "Coach" }).click();
  await page.waitForURL("**/insights/");
  await tabs.getByRole("button", { name: "More" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Wishlist" }).click();
  await page.waitForURL("**/wishlist/");
  await expect(page.getByRole("heading", { name: "Wishlist", level: 1 })).toBeVisible();
});

for (const name of PAGES) {
  test(`${name}: fits the screen and has finger-sized buttons`, async ({ page }) => {
    await page.goto(`/${name}/`);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await page.waitForTimeout(1_500); // charts and lists settle
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "page scrolls sideways").toBeLessThanOrEqual(1);
    const small = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('main [data-slot="button"]')]
        .filter((b) => b.offsetParent !== null)
        .map((b) => ({ text: (b.innerText || b.getAttribute("aria-label") || "").trim(), h: b.getBoundingClientRect().height }))
        .filter((b) => b.h < 36));
    expect(small, "buttons shorter than 36px on a touch screen").toEqual([]);
  });
}
