import { expect, test } from "@playwright/test";

// The labelled demo account: a made-up person's two years of sample messages, for showing every analysis at once.
// Later steps change the demo; the last one resets it.
test.describe.configure({ mode: "serial" });

test("the demo is labelled as sample data and can't connect real sources", async ({ page }) => {
  await page.goto("/dashboard/");
  await expect(page.getByText("Demo account — sample data.")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening), Aarav/ })).toBeVisible();
  for (const label of ["Balance", "Safe to spend this month", "Spent this month", "Next 30 days"]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText("Income and spending by month")).toBeVisible();
  await page.goto("/connections/");
  await expect(page.getByText(/The demo account holds a made-up person's sample messages/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^(Connect|Import a file)$/ })).toHaveCount(0);
  const refused = await page.request.post("/api/v1/ingest/sms/import", { multipart: { file: { name: "x.txt", mimeType: "text/plain", buffer: Buffer.from("VM-HDFCBK-S\nSent Rs.10.00") } }, headers: { "X-Requested-With": "finpilot" } });
  expect(refused.status()).toBe(403);
});

test("the review queue learns: one answer recategorises every payment to that person", async ({ page }) => {
  await page.goto("/review/");
  await page.getByRole("tab", { name: /Categories/ }).click();
  const rows = page.getByRole("listitem").filter({ hasText: "M Selvam" });
  await expect(rows).toHaveCount(2);
  await rows.first().getByRole("combobox").selectOption({ label: "Personal Care" });
  await rows.first().getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved — 1 other M Selvam payment updated too")).toBeVisible();
  await expect(rows).toHaveCount(0);

  await page.getByRole("tab", { name: /Messages/ }).click();
  const refund = page.getByRole("listitem").filter({ hasText: "Refund initiated for your Myntra return" });
  await expect(refund.getByText(/Refund message without a readable amount/)).toBeVisible();
  await refund.getByLabel("Amount (₹)").fill("1899");
  await refund.getByRole("button", { name: "Record as a transaction" }).click();
  await expect(page.getByText("Transaction created")).toBeVisible();
});

test("forecast shows Prophet against baselines, and a what-if", async ({ page }) => {
  await page.goto("/forecast/");
  await expect(page.getByRole("cell", { name: /Prophet \+ known schedule/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Seasonal naive", exact: true })).toBeVisible();
  await page.getByLabel("Amount (₹)").fill("45000");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByText(/(stay above|take you below) your safety buffer/)).toBeVisible();
});

test("subscriptions: dormant gym, converted trial, price rise and overlaps are found", async ({ page }) => {
  await page.goto("/subscriptions/");
  for (const finding of ["Cult.fit: Paying but not using", "Audible: Free trial became paid", "Netflix: Price went up 30%", "Spotify: Two music services"]) {
    await expect(page.getByText(finding)).toBeVisible();
  }
  await page.getByRole("button", { name: "See the email" }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("tax: both years, both regimes, PDF export", async ({ page }) => {
  await page.goto("/tax/");
  await expect(page.getByText(/regime costs ₹[\d,]+ less for you this year/)).toBeVisible();
  await expect(page.getByText("Better for you")).toBeVisible();
  await page.getByRole("tab", { name: "FY 2025-26" }).click();
  await expect(page.getByText(/FY 2025-26 · Income-tax Act, 1961/)).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF summary" }).click();
  expect((await download).suggestedFilename()).toBe("finpilot-tax-2025-26.pdf");
});

test("wishlist: items sorted into tiers against the persona's budget", async ({ page }) => {
  await page.goto("/wishlist/");
  await expect(page.getByText("How much can I spend?")).toBeVisible();
  await expect(page.getByTestId("wish-item").first()).toBeVisible();
  await expect(page.getByRole("region", { name: /Buy now|For your goals|Save up for|Not yet/ }).first()).toBeVisible();
});

test("the coach answers 'can I afford it' and tax questions from the data", async ({ page }) => {
  await page.goto("/insights/");
  await page.getByLabel("Your question").fill("Can I afford a ₹60,000 laptop?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Understood as “Affordability Check”/)).toBeVisible();
  await page.getByLabel("Your question").fill("Which tax regime is better for me?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Understood as “Tax Query”/)).toBeVisible();
});

test("resetting the demo signs out and rebuilds it", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/settings/");
  await page.getByRole("button", { name: "Reset the demo" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reset" }).click();
  await page.waitForURL("**/login/");
  const demo = page.getByRole("button", { name: "Explore the demo account (sample data)" });
  await expect(demo).toBeEnabled({ timeout: 240_000 });
  await demo.click();
  await page.waitForURL("**/dashboard/");
  await expect(page.getByText("Demo account — sample data.")).toBeVisible();
});
