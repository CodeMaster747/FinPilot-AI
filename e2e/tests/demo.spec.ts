import { expect, test } from "@playwright/test";

// The demo script from the plan, in order. Later steps change the demo account; the last one resets it.
test.describe.configure({ mode: "serial" });

test("dashboard shows the demo persona's money at a glance", async ({ page }) => {
  await page.goto("/dashboard/");
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening), Aarav/ })).toBeVisible();
  for (const label of ["Balance", "Safe to spend this month", "Spent this month", "Next 30 days"]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText("Income and spending by month")).toBeVisible();
  await expect(page.getByText("What needs your attention")).toBeVisible();
});

test("a simulated bank SMS becomes a transaction; an OTP is never stored", async ({ page }) => {
  await page.goto("/connections/");
  const phone = page.getByRole("region", { name: "Phone simulator" });
  await phone.getByRole("button", { name: "UPI payment to Swiggy" }).click();
  await phone.getByRole("button", { name: "Send SMS" }).click();
  const outcome = phone.getByTestId("sim-outcome");
  await expect(outcome).toHaveAttribute("data-status", /created|duplicate/);
  await expect(outcome.getByRole("button", { name: /Swiggy/ })).toBeVisible();

  await phone.getByRole("button", { name: "OTP for a card payment" }).click();
  await phone.getByRole("button", { name: "Send SMS" }).click();
  await expect(outcome).toHaveAttribute("data-status", "ignored");
  await expect(outcome).toContainText("not stored");

  await phone.getByRole("button", { name: "Promotional loan offer (-P)" }).click();
  await phone.getByRole("button", { name: "Send SMS" }).click();
  await expect(outcome).toHaveAttribute("data-status", "dropped");
});

test("the order email for that payment adds line items instead of a second transaction", async ({ page }) => {
  await page.goto("/connections/");
  const mail = page.getByRole("region", { name: "Mail simulator" });
  await mail.getByRole("button", { name: "Swiggy receipt for your last order" }).click();
  await mail.getByRole("button", { name: "Deliver email" }).click();
  const outcome = mail.getByTestId("sim-outcome");
  await expect(outcome).toHaveAttribute("data-status", /enriched|duplicate/);
  await outcome.getByRole("button", { name: /Swiggy/ }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("Line items", { exact: true })).toBeVisible();
  await expect(drawer.getByText("Chicken Biryani")).toBeVisible();
  await expect(drawer.getByText(/Evidence \(\d+\)/)).toBeVisible();
});

test("a scanned receipt is read in the browser and attached to its card payment", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/scan/");
  await page.getByRole("button", { name: /Nilgiris supermarket/ }).click();
  await expect(page.getByText("Check and save")).toBeVisible({ timeout: 200_000 });
  const total = await page.getByLabel(/Total \(₹\)/).inputValue();
  const match = page.locator("fieldset").filter({ hasText: "Is this the same as a payment you already have?" });
  await expect(match).toContainText("Nilgiris");
  await expect(match).toContainText(total);
  await expect(match.locator('input[type="radio"]').first()).toBeChecked();
  await page.getByRole("button", { name: "Attach receipt" }).click();
  await expect(page.getByText(/Receipt attached to your .* payment at Nilgiris/)).toBeVisible();
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
  await page.locator('a[href*="export.pdf"]').click();
  expect((await download).suggestedFilename()).toBe("finpilot-tax-2025-26.pdf");
});

test("the coach answers 'can I afford it' from real data", async ({ page }) => {
  await page.goto("/insights/");
  await page.getByLabel("Your question").fill("Can I afford a ₹60,000 laptop?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/Understood as “Affordability Check”/)).toBeVisible();
  await page.getByRole("button", { name: "Which tax regime is better for me?" }).click();
  await expect(page.getByText(/Understood as “Tax Query”/)).toBeVisible();
});

test("Smart Picks shows all three tiers, and a crawl skips the store robots.txt disallows", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/picks/");
  await expect(page.getByText("Comfortable to spend this month")).toBeVisible();
  await expect(page.getByTestId("pick-card").first()).toBeVisible();
  await page.getByRole("tab", { name: /Save up for/ }).click();
  await expect(page.getByTestId("pick-card").filter({ hasText: "Mirrorless" })).toBeVisible();
  await expect(page.getByText(/Save ₹[\d,]+\/month for \d+ month/).first()).toBeVisible();
  await page.getByRole("tab", { name: /For your goals/ }).click();
  await expect(page.getByTestId("pick-card").filter({ hasText: "Laptop" })).toBeVisible();

  await page.getByRole("button", { name: "Crawl now" }).click();
  await expect(page.getByRole("button", { name: "Crawl now" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Crawl now" })).toBeEnabled({ timeout: 150_000 });
  await expect(page.getByText("robots.txt disallows — skipped")).toBeVisible();
  await expect(page.getByText(/\d+ pages · \d+ products · \d+ price changes/).first()).toBeVisible();
});

test("revoking email and deleting its data", async ({ page }) => {
  await page.goto("/connections/");
  const card = page.getByRole("region", { name: "Receipts & bank emails" });
  await card.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Revoke" }).click();
  await expect(card.getByText("Revoked", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Delete data" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete data" }).click();
  await expect(page.getByText(/Deleted [\d,]+ messages/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Mail simulator" }).getByText(/Connect email above/)).toBeVisible();
  await expect(page.getByRole("cell", { name: /Data deleted/ }).first()).toBeVisible();
});

test("resetting the demo signs out and rebuilds it", async ({ page }) => {
  test.setTimeout(300_000);
  await page.goto("/settings/");
  await page.getByRole("button", { name: "Reset the demo" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reset" }).click();
  await page.waitForURL("**/login/");
  await expect(page.getByRole("button", { name: "Try the demo" })).toBeEnabled({ timeout: 240_000 });
  await page.getByRole("button", { name: "Try the demo" }).click();
  await page.waitForURL("**/dashboard/");
  await page.goto("/connections/");
  await expect(page.getByRole("region", { name: "Receipts & bank emails" }).getByText("Connected")).toBeVisible();
});
