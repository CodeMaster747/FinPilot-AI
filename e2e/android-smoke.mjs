// On-device check of the FinPilot Android app, run on an emulator (or a spare test phone) against a FinPilot server.
//
//   1. Fills the phone's SMS inbox with real-format bank alerts, an OTP, a promotion, a personal chat and an alert
//      older than the consent window. Writing to the inbox needs `adb root`, so use an emulator with a
//      "Google APIs" system image (not "Google Play").
//   2. Installs the app fresh, pairs it with the server, creates an account and allows SMS: the consent notice,
//      then Android's own permission dialog.
//   3. Checks on the server that each bank alert became exactly one transaction and nothing else left the phone.
//   4. Plants a new alert while the app is running and checks that it arrives when the app comes back to the front.
//   5. Checks the balance on the dashboard, the Android back button, sharing a PDF export, and signing out and in.
//
// Usage, with the server listening on the laptop:
//   FINPILOT_DATA_DIR=/tmp/fp-android FINPILOT_PORT=8123 FINPILOT_LAN=0 python3 run.py --no-browser
//   FINPILOT_URL=http://localhost:8123 PHONE_URL=http://10.0.2.2:8123 node android-smoke.mjs
// PHONE_URL is the address as the phone sees it (10.0.2.2 is the emulator's name for the laptop).
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _android as android } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SERVER = process.env.FINPILOT_URL ?? "http://localhost:8123";
const PHONE_URL = process.env.PHONE_URL ?? "http://10.0.2.2:8123";
const APK = path.resolve(HERE, "../frontend/android/app/build/outputs/apk/debug/app-debug.apk");
const PKG = "ai.finpilot.app";
const SHOTS = process.env.SHOTS ?? path.join(HERE, "test-results", "android");
const SDK = process.env.ANDROID_HOME ?? path.join(os.homedir(), "Library/Android/sdk");
const ADB = process.env.ADB ?? path.join(SDK, "platform-tools", process.platform === "win32" ? "adb.exe" : "adb");
const EMAIL = `phone-${Date.now()}@finpilot.test`;
const PASSWORD = "phone-test-123";

mkdirSync(SHOTS, { recursive: true });
const adb = (...args) => execFileSync(ADB, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let step = 0;
function ok(cond, what) {
  if (!cond) throw new Error(`FAILED: ${what}`);
  console.log(`  ✓ ${what}`);
}
async function shot(device, name) {
  await device.screenshot({ path: path.join(SHOTS, `${String(++step).padStart(2, "0")}-${name}.png`) });
}

// --- the inbox ------------------------------------------------------------------------------------------------
// Bank formats as they arrive in India (amounts, masks and references are made up). Dates are written in IST.
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function ist(daysAgo, hour = 11) {
  const d = new Date(Date.now() - daysAgo * 86_400_000);
  const local = new Date(d.getTime() + 330 * 60_000); // IST wall clock, read with getUTC*
  local.setUTCHours(hour, 17, 0, 0);
  const ms = local.getTime() - 330 * 60_000;
  const dd = String(local.getUTCDate()).padStart(2, "0");
  const mm = String(local.getUTCMonth() + 1).padStart(2, "0");
  const yy = String(local.getUTCFullYear()).slice(2);
  const mon = MON[local.getUTCMonth()];
  return { ms, dmy: `${dd}/${mm}/${yy}`, dmy2: `${dd}-${mm}-${yy}`, dMonY: `${dd}-${mon}-${yy}`, dMONY: `${dd}-${mon.toUpperCase()}-${yy}` };
}
function inbox() {
  const salary = ist(40, 9), zomato = ist(30, 21), otp = ist(20, 15), bigbasket = ist(20, 16), nach = ist(15, 8), failed = ist(10, 13);
  return [
    { kind: "bank", amount: 85000, address: "VK-HDFCBK-S", at: salary,
      body: `Update! INR 85,000.00 deposited in HDFC Bank A/c XX4521 on ${salary.dMONY} for NEFT Cr-HSBC0560002-ACME SOFTWARE PVT LTD-SALARY-160509419144.Avl bal INR 1,02,450.00. Cheque deposits in A/C are subject to clearing` },
    { kind: "bank", amount: 290, address: "JM-HDFCBK-S", at: zomato,
      body: `Sent Rs.290.00\nFrom HDFC Bank A/C *4521\nTo ZOMATO LTD\nOn ${zomato.dmy}\nRef 224218119562\nNot You?\nCall 1800XXXXXXX/SMS BLOCK UPI to 7308XXXXXX` },
    { kind: "otp", address: "VM-ICICIT-T", at: otp,
      body: "456363 is OTP for txn of INR 2,735.00 at BIGBASKET on ICICI Bank Card XX7788. OTPs are SECRET. DO NOT disclose it to anyone. Bank NEVER asks for OTP." },
    { kind: "bank", amount: 2735, address: "VK-ICICIT-S", at: bigbasket,
      body: `INR 2,735.00 spent using ICICI Bank Card XX7788 on ${bigbasket.dMonY} on BIGBASKET. Avl Limit: INR 1,83,716.00. If not you, call 1800XXXXXXX or SMS BLOCK 7788 to 9215XXXXXX.` },
    { kind: "bank", amount: 6200, address: "JD-SBIINB-S", at: nach,
      body: `Your a/c no. XXXXXXX9034 is debited for Rs.6,200.00 on ${nach.dmy2} by NACH towards SBI EDU LOAN A/C 3345. Avl Bal Rs.45,351.00 -SBI` },
    { kind: "failed", address: "TM-HDFCBK-S", at: failed,
      body: "Your UPI transaction of Rs.1,197.00 to IRCTC E-TICKETING has failed. Any amount debited will be reversed within 3 working days. -HDFC Bank" },
    { kind: "promo", address: "JD-PAYTMB-P", at: ist(5, 12),
      body: "Get cashback up to Rs.250 on electricity bill payment above Rs.999 via Paytm UPI. T&C apply." },
    { kind: "personal", address: "+919876543210", at: ist(3, 19), body: "Hi! Are we still on for lunch on Saturday? Rs 500 each is fine." },
    // 14 months old: outside the default 12-month consent window, so the app must not read it at all.
    { kind: "old", address: "VK-HDFCBK-S", at: ist(430, 9),
      body: "Update! INR 80,000.00 deposited in HDFC Bank A/c XX4521 on 01-AUG-25 for NEFT Cr-HSBC0560002-ACME SOFTWARE PVT LTD-SALARY-150509419144.Avl bal INR 90,000.00." },
  ];
}
// For the device shell: single-quoted, with colons escaped for `content --bind` (it rejects a bare colon in a value).
const quote = (s) => `'${s.replace(/:/g, "\\:").replace(/'/g, `'\\''`)}'`;
function plant({ address, body, at }) {
  const out = adb("shell", ["content insert --uri content://sms/inbox", `--bind address:s:${quote(address)}`, `--bind body:s:${quote(body)}`,
    `--bind date:l:${at.ms}`, `--bind date_sent:l:${at.ms}`, "--bind read:i:1", "--bind seen:i:1", "--bind type:i:1", "2>&1"].join(" "));
  if (/ERROR|usage:/i.test(out)) throw new Error(`couldn't add an SMS to the inbox: ${out.split("\n").pop()}`);
}

// --- the server, as the app's owner would see it -----------------------------------------------------------------
async function serverSession() {
  const res = await fetch(`${SERVER}/api/v1/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-FinPilot-Client": "android" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!res.ok) throw new Error(`login on the server failed: ${res.status} ${await res.text()}`);
  const { access_token: token } = await res.json();
  return async (p) => (await fetch(`${SERVER}/api/v1${p}`, { headers: { Authorization: `Bearer ${token}` } })).json();
}

// --- the run ---------------------------------------------------------------------------------------------------
async function main() {
  ok(existsSync(APK), `the app is built (${path.relative(process.cwd(), APK)})`);
  const health = await (await fetch(`${SERVER}/api/v1/health`)).json();
  ok(health.app === "FinPilot AI", `the server answers at ${SERVER}`);

  console.log("Preparing the phone");
  adb("root");
  adb("wait-for-device");
  try { adb("uninstall", PKG); } catch { /* not installed yet */ }
  adb("install", "-r", APK);
  adb("shell", "content delete --uri content://sms");
  const messages = inbox();
  for (const m of messages) plant(m);
  const count = Number(adb("shell", "content query --uri content://sms/inbox --projection _id | grep -c Row"));
  ok(count === messages.length, `${count} messages planted in the SMS inbox (bank alerts, OTP, promotion, chat, an old alert)`);

  const [device] = await android.devices();
  ok(Boolean(device), `connected to ${device?.model()} (${device?.serial()})`);
  device.setDefaultTimeout(30_000);
  adb("shell", `am start -W -n ${PKG}/.MainActivity`);
  const page = await (await device.webView({ pkg: PKG })).page();
  page.setDefaultTimeout(30_000);

  console.log("Pairing and signing up");
  await page.waitForURL(/\/connect\/$/);
  await shot(device, "connect");
  await page.getByLabel("Or type the address").fill(PHONE_URL);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.waitForURL(/\/login\/$/);
  ok(true, `paired with ${PHONE_URL}`);
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Name").fill("Phone Tester");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL(/\/onboarding\/$/);
  ok(true, "account created from the phone");
  await page.getByRole("button", { name: "Get started" }).click();
  await page.getByRole("button", { name: "Skip", exact: true }).click();

  console.log("Allowing SMS");
  await page.getByRole("button", { name: "Review and allow" }).click();
  const consent = page.getByRole("dialog");
  await consent.getByRole("checkbox", { name: /Record my transactions/ }).click();
  await shot(device, "consent");
  await consent.getByRole("button", { name: "Allow" }).click();
  await page.getByRole("button", { name: "Allow SMS access" }).click();
  await device.wait({ res: "com.android.permissioncontroller:id/permission_allow_button" });
  await shot(device, "android-permission");
  await device.tap({ res: "com.android.permissioncontroller:id/permission_allow_button" });
  ok(true, "Android's SMS permission granted in its own dialog");
  const summary = page.getByText(/alerts read:/);
  await summary.waitFor({ timeout: 120_000 });
  await shot(device, "sms-synced");
  console.log(`    app says: ${await summary.innerText()}`);

  const api = await serverSession();
  const banks = messages.filter((m) => m.kind === "bank");
  const sms = (await api("/sources")).sources.find((s) => s.kind === "sms");
  const last = sms.sync?.last ?? {};
  ok(last.read === messages.length - 1, `the phone read ${last.read} messages: everything except the alert older than the consent window`);
  ok(last.skipped_personal === 1 && last.skipped_otp === 1 && last.skipped_promo === 1,
    "the chat, the OTP and the promotion were dropped on the phone");
  ok(last.uploaded === banks.length + 1, `only the ${last.uploaded} bank alerts were uploaded (including the failed UPI notice)`);
  const txns = await api("/transactions?page_size=100");
  const amounts = txns.items.map((t) => Math.round(Number(t.amount))).sort((a, b) => a - b);
  ok(txns.total === banks.length && JSON.stringify(amounts) === JSON.stringify(banks.map((b) => b.amount).sort((a, b) => a - b)),
    `each bank alert became exactly one transaction (${amounts.map((a) => `₹${a}`).join(", ")}); the failed UPI did not`);
  const salary = txns.items.find((t) => Math.round(Number(t.amount)) === 85000);
  ok(salary?.direction === "credit" && salary?.category?.name === "Salary", `the salary credit is income, categorised "${salary?.category?.name}"`);

  console.log("Finishing setup");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Skip this" }).click();
  await page.getByRole("button", { name: "Go to my dashboard" }).click();
  await page.waitForURL(/\/dashboard\/$/);
  await page.getByText("Safe to spend this month", { exact: true }).first().waitFor();
  await sleep(2_000);
  ok(await page.getByText("Not known yet").count() === 0, "the dashboard knows the balance (from the Avl Bal in the alerts)");
  await shot(device, "dashboard");

  console.log("A new SMS while the app is open");
  const swiggy = ist(0, new Date(Date.now() + 330 * 60_000).getUTCHours());
  swiggy.ms = Date.now() - 5_000;
  plant({ address: "JM-HDFCBK-S", at: swiggy,
    body: `Sent Rs.412.00\nFrom HDFC Bank A/C *4521\nTo SWIGGY\nOn ${swiggy.dmy}\nRef 224218119999\nNot You?\nCall 1800XXXXXXX/SMS BLOCK UPI to 7308XXXXXX` });
  await device.input.press("Home");
  await sleep(1_500);
  adb("shell", `am start -n ${PKG}/.MainActivity`); // back to the front: the app syncs on resume (and every minute)
  let arrived = false;
  for (let i = 0; i < 45 && !arrived; i++) {
    await sleep(2_000);
    arrived = (await api("/transactions?page_size=100")).items.some((t) => Math.round(Number(t.amount)) === 412);
  }
  ok(arrived, "the new ₹412 Swiggy payment reached the server without opening any SMS screen");

  console.log("Navigation, sharing and signing out");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Transactions" }).click();
  await page.waitForURL(/\/transactions\/$/);
  await page.getByText(/^[\d,]+ transactions$/).waitFor();
  await shot(device, "transactions");
  await device.input.press("Back");
  await page.waitForURL(/\/dashboard\/$/);
  ok(true, "Android's back button goes back inside the app");
  const tabs = page.getByRole("navigation", { name: "Main" });
  await tabs.getByRole("button", { name: "More" }).click(); // client-side navigation only: the app has no server routes
  await page.getByRole("dialog").getByRole("link", { name: "Tax" }).click();
  await page.waitForURL(/\/tax\/$/);
  await page.getByRole("button", { name: "PDF summary" }).click();
  let sharing = false; // Android's share sheet: com.android.intentresolver on Android 14+, the system chooser before
  for (let i = 0; i < 20 && !sharing; i++) {
    await sleep(1_000);
    sharing = /intentresolver|ChooserActivity|ResolverActivity/.test(adb("shell", "dumpsys activity activities | grep -E 'topResumedActivity|mResumedActivity'"));
  }
  await shot(device, "share-sheet");
  ok(sharing, "the tax PDF is downloaded with the app's sign-in and handed to Android's share sheet");
  await device.input.press("Back");
  await sleep(1_000);
  await tabs.getByRole("button", { name: "More" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL(/\/login\/$/);
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/dashboard\/$/);
  ok(true, "signed out and back in on the phone");
  console.log(`\nAll checks passed. Screenshots: ${SHOTS}`);
}

// Playwright's Android connection can keep the process alive after the last check, so exit explicitly.
main().then(() => process.exit(0), (e) => {
  console.error(`\n${e.message ?? e}`);
  process.exit(1);
});
