// Visual check: signs in with the demo account and screenshots pages (desktop + one mobile).
// usage: node screenshots.mjs [outDir] [page ...]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.FINPILOT_URL ?? "http://localhost:8000";
const out = process.argv[2] ?? "shots";
const pages = process.argv.slice(3).length ? process.argv.slice(3) : ["dashboard"];
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
await page.goto(`${BASE}/login/`);
await page.screenshot({ path: `${out}/login.png` });
await page.getByRole("button", { name: "Explore the demo account (sample data)" }).click();
await page.waitForURL("**/dashboard/");
for (const p of pages) {
  await page.goto(`${BASE}/${p}/`);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${out}/${p.replace(/\//g, "_")}.png`, fullPage: true });
}
const mobile = await browser.newContext({ viewport: { width: 412, height: 915 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, storageState: await ctx.storageState() });
const mp = await mobile.newPage();
await mp.goto(`${BASE}/${pages[0]}/`);
await mp.waitForLoadState("networkidle");
await mp.waitForTimeout(1200);
await mp.screenshot({ path: `${out}/mobile_${pages[0].replace(/\//g, "_")}.png`, fullPage: true });
console.log(errors.length ? errors.join("\n") : "no browser errors");
await browser.close();
