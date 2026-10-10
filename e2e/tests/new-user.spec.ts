import { expect, test } from "@playwright/test";

test("a new user registers, allows SMS only, loads the sample inbox and sees their own data", async ({ page }) => {
  const email = `e2e-${Date.now()}@finpilot.test`;
  await page.goto("/register/");
  await page.getByLabel("Name").fill("Meera Iyer");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/onboarding/");
  await expect(page.getByRole("heading", { name: /Welcome, Meera/ })).toBeVisible();
  await page.getByRole("button", { name: "Get started" }).click();

  // Nothing is read until consent: "Allow" stays disabled until the required purpose is ticked.
  await page.getByRole("button", { name: "Review and allow" }).click();
  const consent = page.getByRole("dialog");
  await expect(consent.getByText("What is never read")).toBeVisible();
  const allow = consent.getByRole("button", { name: "Allow" });
  await expect(allow).toBeDisabled();
  await consent.getByRole("checkbox", { name: /Record transactions/ }).click();
  await expect(allow).toBeEnabled();
  await allow.click();

  await expect(page.getByText("Allowed. Now bring in some messages")).toBeVisible();
  await page.getByRole("button", { name: /Use the sample inbox/ }).click();
  await expect(page.getByText(/messages read:/)).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/OTPs, promos & non-financial messages ignored/)).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  // Email is a separate permission; skipping it is fine.
  await expect(page.getByRole("heading", { name: "Receipts & bank emails" })).toBeVisible();
  await page.getByRole("button", { name: "Skip this" }).click();
  await expect(page.getByRole("heading", { name: "You're set up" })).toBeVisible();
  await page.getByRole("button", { name: "Go to my dashboard" }).click();
  await page.waitForURL("**/dashboard/");
  await expect(page.getByRole("heading", { name: /Meera/ })).toBeVisible();

  await page.goto("/transactions/");
  await expect(page.getByText(/^[\d,]+ transactions$/)).toBeVisible();
  await page.goto("/connections/");
  await expect(page.getByRole("region", { name: "Bank & payment SMS" }).getByText("Connected")).toBeVisible();
  await expect(page.getByRole("region", { name: "Receipts & bank emails" }).getByText("Not connected")).toBeVisible();
  await expect(page.getByRole("region", { name: "Mail simulator" }).getByText(/Connect email above/)).toBeVisible();
});
