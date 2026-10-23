import path from "node:path";

import { expect, test } from "@playwright/test";

// A brand-new account fed only by real files: an Android "SMS Backup & Restore" export, a receipt photo and typed
// inputs. (On a phone, the Android app reads the inbox directly; a browser has no SMS access, so it imports the
// export the phone would produce.) Nothing here uses the demo's data.
const SAMPLES = path.resolve(__dirname, "../../samples");

test("a new user signs up, imports their SMS, and every page works on their own data", async ({ page }) => {
  test.setTimeout(420_000);
  const email = `e2e-${Date.now()}@finpilot.test`;

  await test.step("register", async () => {
    await page.goto("/register/");
    await page.getByLabel("Name").fill("Meera Iyer");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("e2e-password-123");
    await page.getByRole("button", { name: "Create account" }).click();
    await page.waitForURL("**/onboarding/");
    await expect(page.getByRole("heading", { name: /Welcome, Meera/ })).toBeVisible();
    await page.getByRole("button", { name: "Get started" }).click();
  });

  await test.step("about you: take-home pay, payday and city", async () => {
    await page.getByLabel("Take-home pay per month (₹)").fill("65000");
    await page.getByLabel("Usually paid on day").fill("1");
    await page.getByLabel(/^City/).fill("Chennai");
    await page.getByRole("button", { name: "Save and continue" }).click();
  });

  await test.step("allow SMS (nothing is read before consent) and import the phone's SMS backup", async () => {
    await expect(page.getByRole("heading", { name: "Bank & payment SMS" })).toBeVisible();
    await page.getByRole("button", { name: "Review and allow" }).click();
    const consent = page.getByRole("dialog");
    await expect(consent.getByText("What is never read")).toBeVisible();
    const allow = consent.getByRole("button", { name: "Allow" });
    await expect(allow).toBeDisabled();
    await consent.getByRole("checkbox", { name: /Record my transactions/ }).click();
    await expect(allow).toBeEnabled();
    await allow.click();
    await expect(page.getByText("Allowed.")).toBeVisible();
    await expect(page.getByText(/Open the FinPilot app on your Android phone/)).toBeVisible();

    await page.getByRole("button", { name: "Import a file instead" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.locator('input[type="file"]').setInputFiles(path.join(SAMPLES, "imports/sms_backup.xml"));
    await expect(dialog.getByText(/^302 messages read:/)).toBeVisible({ timeout: 120_000 });
    await expect(dialog.getByText(/new transactions/)).toBeVisible();
    await expect(dialog.getByText(/OTPs, promos & non-financial messages ignored/)).toBeVisible();
    await dialog.getByRole("button", { name: "Close" }).first().click(); // the footer button (the ✕ is also "Close")
    await page.getByRole("button", { name: "Continue" }).click();
  });

  await test.step("email is a separate permission; a mailbox that can't be reached gives a clear error", async () => {
    await expect(page.getByRole("heading", { name: "Receipts & bank emails" })).toBeVisible();
    await page.getByRole("button", { name: "Review and allow" }).click();
    const consent = page.getByRole("dialog");
    await consent.getByRole("checkbox", { name: /Record my transactions/ }).click();
    await consent.getByRole("button", { name: "Allow" }).click();
    await page.getByRole("button", { name: "Connect mailbox" }).click();
    const box = page.getByRole("dialog");
    await box.getByLabel("Email service").selectOption("custom");
    await box.getByLabel("Email address").fill("meera@example.test");
    await box.getByLabel("App password").fill("not-a-real-password");
    await box.getByLabel("IMAP server").fill("127.0.0.1");
    await box.getByLabel("Port").fill("9");
    await box.getByRole("button", { name: "Connect" }).click();
    await expect(page.getByText(/Couldn't reach 127\.0\.0\.1/)).toBeVisible({ timeout: 60_000 });
    await box.getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("button", { name: "Continue" }).click();
  });

  await test.step("dashboard shows the imported money", async () => {
    await expect(page.getByRole("heading", { name: "You're set up" })).toBeVisible();
    await page.getByRole("button", { name: "Go to my dashboard" }).click();
    await page.waitForURL("**/dashboard/");
    await expect(page.getByRole("heading", { name: /Meera/ })).toBeVisible();
    for (const label of ["Balance", "Safe to spend this month", "Spent this month", "Next 30 days"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }
    // The SMS carry "Avl Bal", so the balance is known without asking.
    await expect(page.getByText("Not known yet")).toHaveCount(0);
    await expect(page.getByText("Let's bring in your money")).toHaveCount(0);
  });

  await test.step("transactions list the imported payments", async () => {
    await page.goto("/transactions/");
    await expect(page.getByText(/^[\d,]+ transactions$/)).toBeVisible();
    await expect(page.getByText(/NILGIRIS|Nilgiris/).first()).toBeVisible();
  });

  await test.step("a receipt photo is read in the browser and attached to its card payment", async () => {
    await page.goto("/scan/");
    await page.locator('input[type="file"]').setInputFiles(path.join(SAMPLES, "receipts/nilgiris.png"));
    await expect(page.getByText("Check and save")).toBeVisible({ timeout: 200_000 });
    await expect(page.getByLabel(/Total \(₹\)/)).toHaveValue(/^818(\.0+)?$/);
    await expect(page.getByText("Is this the same as a payment you already have?")).toBeVisible();
    await page.getByRole("button", { name: "Attach receipt" }).click();
    await expect(page.getByText(/Receipt attached to your ₹818 payment/)).toBeVisible();
  });

  await test.step("wishlist: an item is placed in a tier, and any price can be checked", async () => {
    await page.goto("/wishlist/");
    await expect(page.getByText("How much can I spend?")).toBeVisible();
    await page.getByLabel("Item").fill("Running shoes");
    await page.getByLabel("Price").fill("3999");
    await page.getByRole("button", { name: "Add to wishlist" }).click();
    const item = page.getByTestId("wish-item").filter({ hasText: "Running shoes" });
    await expect(item).toBeVisible();
    await expect(page.getByRole("region", { name: /Buy now|Save up for|Not yet/ }).filter({ has: item })).toBeVisible();

    await page.getByRole("button", { name: "Can I afford…?" }).click();
    const check = page.getByRole("dialog");
    await check.getByLabel("Price (₹)").fill("150000");
    await check.getByRole("button", { name: "Check" }).click();
    await expect(check.getByRole("status")).toBeVisible();
    await check.press("Escape");
  });

  await test.step("tax: inputs change the answer, and the PDF downloads", async () => {
    await page.goto("/tax/");
    await expect(page.getByText(/Enter the TDS your employer deducts/)).toBeVisible();
    await page.getByLabel("Gross salary per year (FY 2025-26, from Form 16)").fill("1100000");
    await page.getByLabel("TDS deducted by your employer this year").fill("40000");
    await page.getByRole("button", { name: "Save and recalculate" }).click();
    await expect(page.getByText("Tax details saved")).toBeVisible();
    await expect(page.getByText(/Enter the TDS your employer deducts/)).toHaveCount(0);
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "PDF summary" }).click();
    expect((await download).suggestedFilename()).toBe("finpilot-tax-2026-27.pdf");
  });

  await test.step("the coach answers from this user's data", async () => {
    await page.goto("/insights/");
    await page.getByLabel("Your question").fill("How much did I spend on groceries last month?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(/Understood as “/)).toBeVisible();
  });

  await test.step("pause, revoke and delete the SMS data", async () => {
    await page.goto("/connections/");
    const sms = page.getByRole("region", { name: "Bank & payment SMS" });
    await expect(sms.getByText("Connected", { exact: true })).toBeVisible();
    await sms.getByRole("button", { name: "Pause" }).click();
    await expect(sms.getByText("Paused", { exact: true })).toBeVisible();
    await sms.getByRole("button", { name: "Resume" }).click();
    await expect(sms.getByText("Connected", { exact: true })).toBeVisible();
    await sms.getByRole("button", { name: "Revoke" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Revoke" }).click();
    await expect(sms.getByText("Revoked", { exact: true })).toBeVisible();
    await sms.getByRole("button", { name: "Delete data" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete data" }).click();
    await expect(page.getByText(/Deleted [\d,]+ messages/)).toBeVisible();
  });

  await test.step("delete the account", async () => {
    await page.goto("/settings/");
    await page.getByRole("button", { name: "Delete my account" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
    await dialog.getByRole("button", { name: "Delete everything" }).click();
    await page.waitForURL("**/login/");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("e2e-password-123");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Wrong email or password.")).toBeVisible();
  });
});
