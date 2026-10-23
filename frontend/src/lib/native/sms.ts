// Reading the phone's SMS inbox (Android app only) and sending the financial alerts to the FinPilot server.
// The native plugin filters on the phone: personal chats, promotional (-P) senders and OTPs never leave it.

import { registerPlugin } from "@capacitor/core";

import { api, get, post } from "@/lib/api";
import { isNative } from "@/lib/platform";
import type { Job } from "@/lib/types";

export type PermissionValue = "granted" | "denied" | "prompt" | "prompt-with-rationale";
export type DeviceInfo = { manufacturer: string; model: string; sdk: number; app_version: string };
export type SmsStatus = { permission: PermissionValue; device: DeviceInfo; canAskAgain?: boolean };
type PhoneSms = { address: string; body: string; date_ms: number };
type ReadResult = { messages: PhoneSms[]; read: number; skipped_personal: number; skipped_promo: number; skipped_otp: number; newest_ms: number };

interface SmsInboxPlugin {
  getStatus(): Promise<SmsStatus>;
  requestAccess(): Promise<SmsStatus>;
  countInbox(): Promise<{ total: number; business: number }>;
  read(options: { fromMs: number; toMs: number }): Promise<ReadResult>;
  openAppSettings(): Promise<void>;
}

export const SmsInbox = registerPlugin<SmsInboxPlugin>("SmsInbox");

export type SyncState = {
  status: "not_connected" | "active" | "paused" | "revoked";
  cursor_ms?: number | null;
  backfill_start_ms?: number;
  last_sync_at?: string | null;
  last?: Record<string, number>;
  totals?: Record<string, number>;
};

export type SyncProgress =
  | { phase: "reading"; done: number; total: number; label: string }
  | { phase: "uploading"; done: number; total: number }
  | { phase: "processing"; percent: number; message: string | null };

export type SyncResult = { uploaded: number; read: number; counts: Record<string, number> | null; jobId: number | null };

export class SmsPermissionError extends Error {
  status: SmsStatus;
  constructor(status: SmsStatus) {
    super("FinPilot doesn't have permission to read SMS on this phone yet.");
    this.status = status;
  }
}

const CHUNK = 500;
const MONTH_MS = 31 * 24 * 3600 * 1000;
let running: Promise<SyncResult> | null = null;

function sessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

export async function smsPermission(): Promise<SmsStatus | null> {
  if (!isNative()) return null;
  return SmsInbox.getStatus();
}

export async function requestSmsPermission(): Promise<SmsStatus> {
  return SmsInbox.requestAccess();
}

/** True when Android granted SMS access but no business sender is visible — some phone makers hide them. */
export async function inboxLooksHidden(): Promise<boolean> {
  const { total, business } = await SmsInbox.countInbox();
  return total === 0 || business === 0;
}

async function waitForJob(jobId: number, onProgress?: (p: SyncProgress) => void): Promise<Job> {
  for (let i = 0; i < 900; i++) {
    const job = await get<Job>(`/jobs/${jobId}`);
    if (["done", "failed", "interrupted"].includes(job.status)) return job;
    onProgress?.({ phase: "processing", percent: job.progress, message: job.message });
    await new Promise((r) => setTimeout(r, i < 20 ? 700 : 1500));
  }
  throw new Error("The server is taking unusually long to process your SMS. It will keep going in the background.");
}

async function run(onProgress?: (p: SyncProgress) => void): Promise<SyncResult> {
  const state = await get<SyncState>("/sources/sms/sync-state");
  if (state.status !== "active") return { uploaded: 0, read: 0, counts: null, jobId: null };
  const permission = await SmsInbox.getStatus();
  if (permission.permission !== "granted") throw new SmsPermissionError(permission);

  const now = Date.now() + 60_000;
  const from = Math.max(state.backfill_start_ms ?? 0, (state.cursor_ms ?? 0) + 1);
  const windows: [number, number][] = [];
  for (let start = from; start < now; start += MONTH_MS) windows.push([start, Math.min(start + MONTH_MS, now)]);

  const messages: PhoneSms[] = [];
  const phone = { read: 0, skipped_personal: 0, skipped_promo: 0, skipped_otp: 0 };
  let newest = state.cursor_ms ?? 0;
  for (const [i, [a, b]] of windows.entries()) {
    onProgress?.({ phase: "reading", done: i, total: windows.length,
      label: new Date(a).toLocaleDateString("en-IN", { month: "long", year: "numeric" }) });
    const r = await SmsInbox.read({ fromMs: a, toMs: b });
    messages.push(...r.messages);
    phone.read += r.read;
    phone.skipped_personal += r.skipped_personal;
    phone.skipped_promo += r.skipped_promo;
    phone.skipped_otp += r.skipped_otp;
    newest = Math.max(newest, r.newest_ms);
  }
  if (messages.length === 0) {
    return { uploaded: 0, read: phone.read, counts: null, jobId: null };  // nothing new: no server work needed
  }

  const session = sessionId();
  for (let i = 0; i < messages.length; i += CHUNK) {
    onProgress?.({ phase: "uploading", done: i, total: messages.length });
    await post("/ingest/sms/device", { session, messages: messages.slice(i, i + CHUNK), final: false });
  }
  onProgress?.({ phase: "uploading", done: messages.length, total: messages.length });
  const device = permission.device;
  const done = await api<{ job_id: number }>("/ingest/sms/device", {
    method: "POST",
    body: { session, messages: [], final: true, cursor_ms: newest || null, phone,
            device: { manufacturer: device.manufacturer, model: device.model, sdk: device.sdk, app_version: device.app_version } },
  });
  const job = await waitForJob(done.job_id, onProgress);
  if (job.status !== "done") throw new Error(job.error || "The server couldn't process your SMS. Try Sync now again.");
  return { uploaded: messages.length, read: phone.read, counts: (job.result as { counts?: Record<string, number> })?.counts ?? null, jobId: job.id };
}

/** Reads new SMS and sends them to the server. Only one sync runs at a time; a second caller shares the first one. */
export function syncSms(onProgress?: (p: SyncProgress) => void): Promise<SyncResult> {
  if (!isNative()) return Promise.reject(new Error("Reading SMS needs the FinPilot Android app."));
  if (!running) {
    running = run(onProgress).finally(() => {
      running = null;
    });
  }
  return running;
}

export function syncInProgress(): boolean {
  return running !== null;
}
