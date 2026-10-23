"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban, CircleAlert, CircleCheck, CirclePause, ExternalLink, FileUp, KeyRound, LoaderCircle, Mail, MessageSquareText, RefreshCw,
  Settings2, Smartphone, X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { NativeSelect, Pill } from "@/components/common";
import { JobProgress } from "@/components/job-progress";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, del, get, post } from "@/lib/api";
import { ago } from "@/lib/format";
import {
  inboxLooksHidden, requestSmsPermission, SmsInbox, SmsPermissionError, smsPermission, type SmsStatus, syncSms, type SyncProgress,
  type SyncResult,
} from "@/lib/native/sms";
import { isNative } from "@/lib/platform";
import type { Notice, Source } from "@/lib/types";

export type Kind = "sms" | "email";
export const ICON = { sms: MessageSquareText, email: Mail };
export const REFRESH = [["sources"], ["sources-history"], ["transactions"], ["dashboard"], ["review-counts"], ["review"], ["me"], ["accounts"],
  ["forecast"], ["subscriptions"], ["insights"], ["wishlist"], ["mailbox"]];

export function useRefresh() {
  const qc = useQueryClient();
  return useCallback(() => { for (const k of REFRESH) qc.invalidateQueries({ queryKey: k }); }, [qc]);
}

export function StatusPill({ status }: { status: Source["status"] }) {
  if (status === "active") return <Pill tone="good"><CircleCheck className="size-3" /> Connected</Pill>;
  if (status === "paused") return <Pill tone="warn"><CirclePause className="size-3" /> Paused</Pill>;
  if (status === "revoked") return <Pill tone="bad"><Ban className="size-3" /> Revoked</Pill>;
  return <Pill>Not connected</Pill>;
}

// ---------------------------------------------------------------------------------------------
// Consent dialog: itemised notice, the purpose, backfill window

function NoticeSection({ title, items, tone }: { title: string; items: string[]; tone?: "no" }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</div>
      <ul className="grid gap-1">
        {items.map((s) => (
          <li key={s} className="flex gap-2 text-sm">
            {tone === "no" ? <X className="mt-0.5 size-3.5 shrink-0 text-[var(--critical)]" /> : <CircleCheck className="mt-0.5 size-3.5 shrink-0 text-[var(--good)]" />}
            <span>{s}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ConsentDialog({ kind, open, onOpenChange, onGranted }: { kind: Kind; open: boolean; onOpenChange: (o: boolean) => void; onGranted?: () => void }) {
  const refresh = useRefresh();
  const notice = useQuery({ queryKey: ["notice", kind], queryFn: () => get<Notice>(`/sources/${kind}/notice`), enabled: open });
  const [purposes, setPurposes] = useState<Record<string, boolean>>({});
  const [backfill, setBackfill] = useState("12");
  const grant = useMutation({
    mutationFn: () => post<Source>(`/sources/${kind}/grant`, { purposes: Object.keys(purposes).filter((p) => purposes[p]), backfill_months: Number(backfill) }),
    onSuccess: () => { toast.success(`${notice.data?.title ?? kind} connected`); refresh(); onOpenChange(false); onGranted?.(); },
    onError: (e) => toast.error((e as Error).message),
  });
  const n = notice.data;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Allow FinPilot to read your {kind === "sms" ? "bank & payment SMS" : "receipts & bank emails"}?</DialogTitle>
          <DialogDescription>Nothing is read until you agree. You can pause, revoke or delete this data at any time from Connections.</DialogDescription>
        </DialogHeader>
        {!n ? <LoaderCircle className="mx-auto size-5 animate-spin" /> : (
          <div className="grid gap-4">
            <NoticeSection title="What is read" items={n.reads} />
            <NoticeSection title="What is never read" items={n.never_reads} tone="no" />
            <NoticeSection title="What is stored" items={n.stores} />
            <NoticeSection title="FinPilot will never" items={n.never} tone="no" />
            <fieldset className="grid gap-2 rounded-lg border border-border p-3">
              <legend className="px-1 text-sm font-medium">What this data is used for</legend>
              {Object.entries(n.purposes).map(([key, text]) => (
                <label key={key} className="flex items-start gap-3 text-sm">
                  <Checkbox className="mt-0.5" checked={Boolean(purposes[key])} onCheckedChange={(v) => setPurposes({ ...purposes, [key]: Boolean(v) })} aria-label={text} />
                  <span>{text}</span>
                </label>
              ))}
            </fieldset>
            <label className="flex flex-wrap items-center gap-2 text-sm">
              Read messages from the last
              <NativeSelect value={backfill} onChange={(e) => setBackfill(e.target.value)} aria-label="Backfill window">
                {[1, 3, 6, 12, 24].map((m) => <option key={m} value={m}>{m} month{m > 1 ? "s" : ""}</option>)}
              </NativeSelect>
              and everything new from now on.
            </label>
            <p className="text-xs text-muted-foreground">12 months gives the forecast and the tax estimate a full year to learn from. Notice version {n.version} · fingerprint {n.hash.slice(0, 12)} — recorded with your choice in the consent history.</p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Not now</Button>
          <Button onClick={() => grant.mutate()} disabled={!purposes.transactions || grant.isPending}>
            {grant.isPending && <LoaderCircle className="animate-spin" />} Allow
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------------------
// Import a file (SMS backup XML / CSV / pasted text, or .eml / .mbox)

export function ImportDialog({ kind, open, onOpenChange }: { kind: Kind; open: boolean; onOpenChange: (o: boolean) => void }) {
  const refresh = useRefresh();
  const [jobId, setJobId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [paste, setPaste] = useState("");

  async function upload(file: File) {
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api<{ job_id: number; messages: number }>(`/ingest/${kind}/import`, { method: "POST", body: fd });
      setJobId(r.job_id);
      toast.message(`Reading ${r.messages} messages…`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const accept = kind === "sms" ? ".xml,.csv,.txt" : ".eml,.mbox,.txt";
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setJobId(null); setPaste(""); } }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import {kind === "sms" ? "SMS" : "emails"} from a file</DialogTitle>
          <DialogDescription>
            {kind === "sms"
              ? "An Android “SMS Backup & Restore” XML file, a CSV export (date, sender, message), or messages pasted as text."
              : "A single email (.eml) or a mailbox archive (.mbox) — for example a Google Takeout export of your bank label."}{" "}
            Every message goes through the same filters as the live feed: OTPs, promotions and personal messages are dropped.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border p-6 text-center hover:bg-muted">
            {busy ? <LoaderCircle className="size-6 animate-spin" /> : <FileUp className="size-6 text-muted-foreground" />}
            <span className="text-sm font-medium">Choose a file</span>
            <span className="text-xs text-muted-foreground">{accept.replaceAll(",", "  ")}</span>
            <input type="file" accept={accept} className="sr-only" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          {kind === "sms" && (
            <div className="grid gap-2">
              <Textarea rows={4} value={paste} onChange={(e) => setPaste(e.target.value)} aria-label="Paste messages"
                placeholder={"Or paste messages, separated by a blank line. Optional first line: the sender, e.g.\nVM-HDFCBK-S\nSent Rs.250.00 From HDFC Bank A/C *4521 To ZOMATO…"} />
              <Button variant="outline" disabled={!paste.trim() || busy} onClick={() => upload(new File([paste], "pasted.txt", { type: "text/plain" }))}>Import pasted text</Button>
            </div>
          )}
          <JobProgress jobId={jobId} invalidate={REFRESH} label="Reading your file" />
        </div>
        <DialogFooter><Button variant="outline" onClick={() => { onOpenChange(false); refresh(); }}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------------------
// SMS from this phone (Android app)

function syncLine(p: SyncProgress): string {
  if (p.phase === "reading") return `Reading SMS from ${p.label}… (${p.done + 1} of ${p.total})`;
  if (p.phase === "uploading") return `Sending ${p.total.toLocaleString("en-IN")} bank and payment alerts to your FinPilot server…`;
  return p.message ? `${p.message}…` : "Turning them into transactions…";
}

function syncPercent(p: SyncProgress): number {
  if (p.phase === "reading") return 5 + (p.done / Math.max(1, p.total)) * 35;
  if (p.phase === "uploading") return 40 + (p.done / Math.max(1, p.total)) * 20;
  return 60 + p.percent * 0.4;
}

function PermissionHelp({ status, onOpenSettings, onCheck }: { status: SmsStatus; onOpenSettings: () => void; onCheck: () => void }) {
  const sdk = status.device?.sdk ?? 0;
  return (
    <div className="grid gap-3 rounded-lg border border-[#f3dfa6] bg-[#fefaf0] p-3 text-sm text-[#5c3d00]">
      <div className="flex items-center gap-2 font-medium"><CircleAlert className="size-4 shrink-0" /> Android hasn&apos;t given FinPilot access to SMS</div>
      <ol className="grid list-decimal gap-1 pl-5">
        <li>Tap <span className="font-medium">Open app settings</span>.</li>
        {sdk >= 33 && (
          <li>If SMS shows <span className="font-medium">“Restricted setting”</span> (apps installed outside the Play Store): tap the <span className="font-medium">⋮</span> menu at the top right → <span className="font-medium">Allow restricted settings</span>, and confirm with your PIN or fingerprint.</li>
        )}
        <li>Tap <span className="font-medium">Permissions → SMS → Allow</span>.</li>
        <li>Come back here and tap <span className="font-medium">Check again</span>.</li>
      </ol>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={onOpenSettings}><Settings2 /> Open app settings</Button>
        <Button size="sm" variant="outline" onClick={onCheck}><RefreshCw /> Check again</Button>
      </div>
    </div>
  );
}

function HiddenInboxHelp({ manufacturer, onCheck }: { manufacturer?: string; onCheck: () => void }) {
  const xiaomi = /xiaomi|redmi|poco/i.test(manufacturer ?? "");
  return (
    <div className="grid gap-2 rounded-lg border border-[#f3dfa6] bg-[#fefaf0] p-3 text-sm text-[#5c3d00]">
      <div className="flex items-center gap-2 font-medium"><CircleAlert className="size-4 shrink-0" /> FinPilot can&apos;t see any bank messages on this phone</div>
      {xiaomi ? (
        <p>Xiaomi, Redmi and POCO phones hide bank alerts from apps by default. Open <span className="font-medium">Settings → Apps → FinPilot AI → Other permissions</span> and allow <span className="font-medium">“Read notification SMS”</span> (sometimes called “Service SMS”).</p>
      ) : (
        <p>Check that your bank&apos;s messages are in the phone&apos;s SMS inbox (not only in a spam folder), and that FinPilot&apos;s SMS permission is allowed in Settings → Apps → FinPilot AI.</p>
      )}
      <div><Button size="sm" variant="outline" onClick={onCheck}><RefreshCw /> Check again</Button></div>
    </div>
  );
}

export function SmsPhoneSync({ source, autoStart = false, onSynced }: { source?: Source; autoStart?: boolean; onSynced?: (r: SyncResult) => void }) {
  const refresh = useRefresh();
  const [perm, setPerm] = useState<SmsStatus | null>(null);
  const [hidden, setHidden] = useState(false);
  const [progress, setProgress] = useState<SyncProgress | null>(null);
  const [result, setResult] = useState<SyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const active = source?.status === "active";

  const check = useCallback(async () => {
    const s = await smsPermission();
    setPerm(s);
    if (s?.permission === "granted") setHidden(await inboxLooksHidden().catch(() => false));
    return s;
  }, []);

  const run = useCallback(async () => {
    setError(null);
    setResult(null);
    setProgress({ phase: "reading", done: 0, total: 1, label: "your inbox" });
    try {
      const r = await syncSms(setProgress);
      setResult(r);
      refresh();
      onSynced?.(r);
    } catch (e) {
      if (e instanceof SmsPermissionError) setPerm(e.status);
      else setError((e as Error).message);
    } finally {
      setProgress(null);
    }
  }, [refresh, onSynced]);

  useEffect(() => {
    let cancelled = false;
    smsPermission().then(async (s) => {
      if (cancelled) return;
      setPerm(s);
      if (s?.permission !== "granted") return;
      const looksHidden = await inboxLooksHidden().catch(() => false);
      if (cancelled) return;
      setHidden(looksHidden);
      if (autoStart && active && !looksHidden) run();
    });
    return () => { cancelled = true; };
  }, [run, autoStart, active]);

  async function allow() {
    const s = await requestSmsPermission();
    setPerm(s);
    if (s.permission === "granted") {
      const looksHidden = await inboxLooksHidden().catch(() => false);
      setHidden(looksHidden);
      if (!looksHidden) await run();
    }
  }

  if (!active) return null;
  const granted = perm?.permission === "granted";
  const last = source?.sync?.last ?? {};
  return (
    <div className="grid gap-3">
      {!granted && perm && perm.permission !== "denied" && (
        <div className="grid gap-2 rounded-lg bg-muted p-3 text-sm">
          <div className="flex items-start gap-2"><Smartphone className="mt-0.5 size-4 shrink-0" />
            <span>Android will now ask whether FinPilot may read SMS. Only bank, card, wallet and biller alerts are sent to your FinPilot server — chats, OTPs and promotions are dropped on the phone.</span>
          </div>
          <div><Button onClick={allow}><MessageSquareText /> Allow SMS access</Button></div>
        </div>
      )}
      {!granted && perm?.permission === "denied" && (
        <PermissionHelp status={perm} onOpenSettings={() => SmsInbox.openAppSettings()} onCheck={async () => {
          const s = await check();
          if (s?.permission === "granted") run();
        }} />
      )}
      {granted && hidden && <HiddenInboxHelp manufacturer={perm?.device?.manufacturer} onCheck={async () => {
        const s = await check();
        if (s?.permission === "granted" && !(await inboxLooksHidden().catch(() => true))) run();
      }} />}
      {progress && (
        <div className="grid gap-1.5 rounded-lg bg-muted p-3 text-sm" role="status">
          <div className="flex items-center gap-2"><LoaderCircle className="size-4 animate-spin" /> {syncLine(progress)}</div>
          <div className="h-1.5 overflow-hidden rounded-full bg-border">
            <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.max(4, syncPercent(progress))}%` }} />
          </div>
        </div>
      )}
      {result && !progress && (
        <div className="flex items-start gap-2 rounded-lg bg-[#e7f5e7] p-3 text-sm text-[var(--good-text)]" role="status">
          <CircleCheck className="mt-0.5 size-4 shrink-0" />
          <span>{result.uploaded === 0
            ? `Up to date — checked ${result.read.toLocaleString("en-IN")} messages, nothing new from your bank.`
            : `${result.uploaded.toLocaleString("en-IN")} alerts read: ${(result.counts?.transactions ?? 0).toLocaleString("en-IN")} new transactions, ${(result.counts?.linked ?? 0).toLocaleString("en-IN")} linked to ones already recorded, ${(result.counts?.review ?? 0).toLocaleString("en-IN")} to review.`}</span>
        </div>
      )}
      {error && <p className="rounded-lg bg-[#fbe4e4] p-3 text-sm text-[#a32525]" role="alert">{error}</p>}
      {granted && (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={run} disabled={progress !== null}>{progress ? <LoaderCircle className="animate-spin" /> : <RefreshCw />} Sync now</Button>
          <span className="text-xs text-muted-foreground">
            {source?.sync?.last_sync_at ? `Last synced ${ago(source.sync.last_sync_at)}` : "Not synced yet"} · new messages are read whenever you open the app
          </span>
        </div>
      )}
      {granted && Object.keys(last).length > 0 && (
        <dl className="grid grid-cols-2 gap-2 text-center sm:grid-cols-4" aria-label="Capture health (last sync)">
          {[["Read on phone", last.read], ["Chats, OTPs & promos skipped", (last.skipped_personal ?? 0) + (last.skipped_otp ?? 0) + (last.skipped_promo ?? 0)],
            ["New transactions", last.transactions], ["Sent to review", last.review]].map(([k, v]) => (
            <div key={String(k)} className="rounded-lg bg-muted px-2 py-2">
              <dd className="text-base font-semibold tabular">{Number(v ?? 0).toLocaleString("en-IN")}</dd>
              <dt className="text-[11px] leading-tight text-muted-foreground">{k}</dt>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Email: an IMAP mailbox signed in with an app password

type Provider = { id: string; label: string; host: string | null; port: number; help: string };

export function MailboxDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const refresh = useRefresh();
  const providers = useQuery({ queryKey: ["mail-providers"], queryFn: () => get<{ providers: Provider[] }>("/sources/email/providers"), enabled: open });
  const [form, setForm] = useState({ provider: "gmail", email: "", password: "", host: "", port: "993" });
  const [jobId, setJobId] = useState<number | null>(null);
  const connect = useMutation({
    mutationFn: () => post<{ job_id: number }>("/sources/email/mailbox", {
      provider: form.provider, email: form.email.trim(), password: form.password,
      ...(form.provider === "custom" ? { host: form.host.trim(), port: Number(form.port) || 993 } : {}),
    }),
    onSuccess: (r) => { setJobId(r.job_id); setForm((f) => ({ ...f, password: "" })); refresh(); toast.success("Mailbox connected — reading your bank and shop emails"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const provider = providers.data?.providers.find((p) => p.id === form.provider);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setJobId(null); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Connect your mailbox</DialogTitle>
          <DialogDescription>
            FinPilot signs in with an <span className="font-medium">app password</span> — a separate password you create for it and can delete any time.
            It only opens emails from banks, card issuers, shops and billers, never marks anything as read, and never sends, moves or deletes email.
          </DialogDescription>
        </DialogHeader>
        {jobId ? (
          <div className="grid gap-3">
            <JobProgress jobId={jobId} invalidate={REFRESH} label="Reading your bank and shop emails" />
            <p className="text-xs text-muted-foreground">New emails are read every 30 minutes while your FinPilot server runs.</p>
          </div>
        ) : (
          <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); connect.mutate(); }}>
            <label className="grid gap-1 text-sm">Email service
              <NativeSelect value={form.provider} onChange={set("provider")} aria-label="Email service">
                {(providers.data?.providers ?? [{ id: "gmail", label: "Gmail" } as Provider]).map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </NativeSelect>
            </label>
            <label className="grid gap-1 text-sm">Email address
              <Input type="email" required autoComplete="email" inputMode="email" value={form.email} onChange={set("email")} placeholder="you@gmail.com" />
            </label>
            <label className="grid gap-1 text-sm">App password
              <Input type="password" required autoComplete="off" value={form.password} onChange={set("password")} placeholder="abcd efgh ijkl mnop" />
            </label>
            {form.provider === "custom" && (
              <div className="grid grid-cols-[1fr_6rem] gap-2">
                <label className="grid gap-1 text-sm">IMAP server<Input required value={form.host} onChange={set("host")} placeholder="imap.example.com" /></label>
                <label className="grid gap-1 text-sm">Port<Input inputMode="numeric" value={form.port} onChange={set("port")} /></label>
              </div>
            )}
            <div className="grid gap-1 rounded-lg bg-muted p-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground"><KeyRound className="size-3.5" /> How to get an app password</span>
              <span>{provider?.help ?? "Create an app password in your email account's security settings."}</span>
              {form.provider === "gmail" && (
                <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-primary underline">
                  Open Google App passwords <ExternalLink className="size-3" />
                </a>
              )}
              <span>Outlook.com and Hotmail can&apos;t be connected (Microsoft no longer allows app passwords); forward bank emails to Gmail, or import .eml/.mbox files.</span>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button type="submit" disabled={connect.isPending}>{connect.isPending && <LoaderCircle className="animate-spin" />} Connect</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function MailboxPanel({ source }: { source?: Source }) {
  const refresh = useRefresh();
  const [open, setOpen] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const box = source?.mailbox;
  const sync = useMutation({
    mutationFn: () => post<{ job_id: number }>("/sources/email/sync"),
    onSuccess: (r) => setJobId(r.job_id),
    onError: (e) => toast.error((e as Error).message),
  });
  const disconnect = useMutation({
    mutationFn: () => del("/sources/email/mailbox"),
    onSuccess: () => { refresh(); toast.success("Mailbox disconnected — the app password was deleted from FinPilot"); },
  });
  if (source?.status !== "active") return null;
  if (!box) {
    return (
      <div className="grid gap-2 rounded-lg bg-muted p-3 text-sm">
        <span>Sign in to your mailbox so FinPilot can read bank alerts, order receipts and bills automatically.</span>
        <div><Button onClick={() => setOpen(true)}><Mail /> Connect mailbox</Button></div>
        <MailboxDialog open={open} onOpenChange={setOpen} />
      </div>
    );
  }
  const c = box.last_counts ?? {};
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <Mail className="size-4 text-muted-foreground" />
        <span className="font-medium">{box.username}</span>
        <span className="text-muted-foreground">· {box.provider_label} · {box.last_synced_at ? `read ${ago(box.last_synced_at)}` : "first sync running"}</span>
      </div>
      {box.last_error && <p className="rounded-lg bg-[#fbe4e4] p-3 text-sm text-[#a32525]" role="alert">{box.last_error}</p>}
      {Object.keys(c).length > 0 && (
        <p className="text-xs text-muted-foreground">
          Last sync: {c.emails ?? 0} emails · {c.transactions ?? 0} new transactions · {c.linked ?? 0} added to payments · {c.waiting ?? 0} waiting for their bank alert
        </p>
      )}
      <JobProgress jobId={jobId} invalidate={REFRESH} label="Reading your bank and shop emails" />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => sync.mutate()} disabled={sync.isPending}><RefreshCw /> Sync now</Button>
        <Button variant="outline" onClick={() => setOpen(true)}>Change password</Button>
        <Button variant="outline" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>Disconnect</Button>
      </div>
      <MailboxDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

export function isPhoneApp(): boolean {
  return isNative();
}
