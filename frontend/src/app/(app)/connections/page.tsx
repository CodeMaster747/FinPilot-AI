"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CirclePause, CirclePlay, FileUp, History, Inbox, LoaderCircle, Send, ShieldCheck, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Card, Pill } from "@/components/common";
import { Confirm } from "@/components/confirm";
import { JobProgress } from "@/components/job-progress";
import { FieldList, HighlightedText } from "@/components/message-view";
import { ConsentDialog, ICON, ImportDialog, type Kind, REFRESH, StatusPill, useRefresh } from "@/components/sources";
import { TxnDrawer } from "@/components/txn-drawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { get, post, put } from "@/lib/api";
import { ago, fmtDate, inr, titleCase } from "@/lib/format";
import type { Message, SimOutcome, Source } from "@/lib/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------------------------
// Source card

function SourceCard({ s }: { s: Source }) {
  const refresh = useRefresh();
  const [consent, setConsent] = useState(false);
  const [importing, setImporting] = useState(false);
  const [confirm, setConfirm] = useState<null | "revoke" | "delete">(null);
  const [jobId, setJobId] = useState<number | null>(null);
  const Icon = ICON[s.kind];
  const act = useMutation({
    mutationFn: (action: string) => post<{ deleted?: Record<string, number> }>(`/sources/${s.kind}/${action}`),
    onSuccess: (r, action) => {
      refresh();
      setConfirm(null);
      if (action === "delete-data" && r.deleted) {
        toast.success(`Deleted ${r.deleted.messages} messages and ${r.deleted.transactions_deleted} transactions that came only from ${s.title}.`
          + (r.deleted.transactions_kept ? ` ${r.deleted.transactions_kept} transactions also confirmed by another source were kept.` : ""));
      } else toast.success({ pause: "Paused — nothing new will be read", resume: "Resumed", revoke: "Permission revoked" }[action] ?? "Done");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const sample = useMutation({
    mutationFn: () => post<{ job_id: number }>(`/ingest/${s.kind}/sample`),
    onSuccess: (r) => setJobId(r.job_id),
    onError: (e) => toast.error((e as Error).message),
  });
  const purposes = useMutation({
    mutationFn: (picks: boolean) => put(`/sources/${s.kind}/purposes`, { purposes: picks ? ["transactions", "picks"] : ["transactions"] }),
    onSuccess: (_, picks) => { refresh(); toast.success(picks ? "Smart Picks may now use this source" : "Smart Picks will no longer use this source"); },
  });
  const c = s.counts ?? {};
  const connected = s.status === "active" || s.status === "paused";
  return (
    <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5" aria-label={s.title}>
      <div className="flex items-start gap-3">
        <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-secondary text-secondary-foreground"><Icon className="size-5" /></div>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{s.title}</h2>
          <p className="text-sm text-muted-foreground">
            {s.kind === "sms" ? "Bank, card, UPI and biller alerts — the most complete record of your spending." : "Order receipts with line items, bills, statements and subscription notices."}
          </p>
        </div>
        <StatusPill status={s.status} />
      </div>

      {connected && (
        <>
          <dl className="grid grid-cols-3 gap-2 text-center">
            {[["Messages kept", c.messages ?? 0], ["Linked to payments", (c.linked ?? 0) + (c.enriched ?? 0)], ["In review", c.needs_review ?? 0]].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-muted px-2 py-2">
                <dd className="text-lg font-semibold tabular">{Number(v).toLocaleString("en-IN")}</dd>
                <dt className="text-xs text-muted-foreground">{k}</dt>
              </div>
            ))}
          </dl>
          <div className="grid gap-1 text-sm text-muted-foreground">
            <div>Allowed {fmtDate(s.granted_at, "d MMM yyyy")} · reads the last {s.backfill_months} months · last read {ago(s.last_ingest_at)}</div>
            <label className="flex items-center gap-2 text-foreground">
              <Switch checked={s.purposes.includes("picks")} onCheckedChange={(v) => purposes.mutate(Boolean(v))} disabled={purposes.isPending} aria-label="Use for Smart Picks" />
              Also use for Smart Picks recommendations
            </label>
          </div>
        </>
      )}
      {s.status === "paused" && <p className="rounded-lg bg-[#fdf2d6] p-2 text-sm text-[#7a5200]">Paused: new messages are refused until you resume. Existing data is kept.</p>}
      {s.status === "revoked" && <p className="rounded-lg bg-muted p-2 text-sm text-muted-foreground">Permission revoked: nothing is read. Data already captured is kept until you delete it.</p>}

      <JobProgress jobId={jobId} invalidate={REFRESH} label="Reading the sample inbox" />

      <div className="mt-auto flex flex-wrap gap-2">
        {(s.status === "not_connected" || s.status === "revoked") && (
          <Button onClick={() => setConsent(true)}><ShieldCheck /> {s.status === "revoked" ? "Reconnect" : "Connect"}</Button>
        )}
        {s.status === "active" && (
          <>
            <Button onClick={() => sample.mutate()} disabled={sample.isPending}><Inbox /> Load sample {s.kind === "sms" ? "inbox" : "mailbox"}</Button>
            <Button variant="outline" onClick={() => setImporting(true)}><FileUp /> Import a file</Button>
            <Button variant="outline" onClick={() => act.mutate("pause")}><CirclePause /> Pause</Button>
          </>
        )}
        {s.status === "paused" && <Button variant="outline" onClick={() => act.mutate("resume")}><CirclePlay /> Resume</Button>}
        {connected && <Button variant="outline" onClick={() => setConfirm("revoke")}><Ban /> Revoke</Button>}
        {s.status !== "not_connected" && (c.messages ?? 0) > 0 && (
          <Button variant="destructive" onClick={() => setConfirm("delete")}><Trash2 /> Delete data</Button>
        )}
      </div>

      <ConsentDialog kind={s.kind} open={consent} onOpenChange={setConsent} />
      <ImportDialog kind={s.kind} open={importing} onOpenChange={setImporting} />
      <Confirm open={confirm === "revoke"} onOpenChange={(o) => !o && setConfirm(null)} title={`Revoke access to ${s.title}?`}
        confirmLabel="Revoke" busy={act.isPending} onConfirm={() => act.mutate("revoke")}>
        FinPilot stops reading this source immediately. What was already captured stays until you choose “Delete data”.
      </Confirm>
      <Confirm open={confirm === "delete"} onOpenChange={(o) => !o && setConfirm(null)} title={`Delete everything from ${s.title}?`}
        confirmLabel="Delete data" destructive busy={act.isPending} onConfirm={() => act.mutate("delete-data")}>
        This removes all {(c.messages ?? 0).toLocaleString("en-IN")} stored messages and every transaction that exists only because of them.
        Transactions also confirmed by another source (for example a bank SMS for an emailed receipt) are kept. This can&apos;t be undone.
      </Confirm>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
// Live simulator: one message through exactly the same pipeline

type Template = { id: string; channel: Kind; group: string; label: string; sender: string; body?: string; subject?: string; html?: string };
type Outcome = SimOutcome & { message_id?: number | null };

const OUTCOME: Record<string, { title: string; tone: "good" | "blue" | "warn" | "neutral" }> = {
  created: { title: "New transaction recorded", tone: "good" },
  duplicate: { title: "Already recorded — linked as evidence, not double-counted", tone: "blue" },
  enriched: { title: "Receipt attached to the matching payment", tone: "good" },
  transfer: { title: "Recorded as a transfer", tone: "blue" },
  reversed: { title: "Reversal applied", tone: "warn" },
  informational: { title: "Noted (no transaction)", tone: "neutral" },
  review: { title: "Sent to the review queue", tone: "warn" },
  pending: { title: "Saved — waiting for the bank alert", tone: "neutral" },
  ignored: { title: "Ignored and not stored", tone: "neutral" },
  dropped: { title: "Dropped before reading", tone: "neutral" },
};

function OutcomeCard({ o, onOpen }: { o: Outcome; onOpen: (id: number) => void }) {
  const stored = useQuery({ queryKey: ["message", o.message_id], queryFn: () => get<Message>(`/messages/${o.message_id}`), enabled: !!o.message_id });
  const meta = OUTCOME[o.status] ?? { title: titleCase(o.status), tone: "neutral" };
  const tones = { good: "border-[#bfe3bf] bg-[#f3faf3]", blue: "border-[#c9dcf3] bg-[#f3f7fd]", warn: "border-[#f3dfa6] bg-[#fefaf0]", neutral: "border-border bg-muted/50" };
  return (
    <div className={cn("grid gap-3 rounded-xl border p-4", tones[meta.tone])} data-testid="sim-outcome" data-status={o.status}>
      <div>
        <div className="font-semibold">{meta.title}</div>
        <div className="text-sm text-muted-foreground">{o.detail}</div>
      </div>
      {o.kind && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          <Pill tone="blue">Classified: {titleCase(o.kind)} · {Math.round((o.confidence ?? 0) * 100)}%</Pill>
          {o.parser && <Pill>Parser: {o.parser}</Pill>}
        </div>
      )}
      {stored.data?.body && <div className="rounded-lg bg-card p-3 ring-1 ring-border"><HighlightedText text={stored.data.body} fields={stored.data.fields} /></div>}
      {o.fields && Object.keys(o.fields).length > 0 && <FieldList fields={o.fields} />}
      {o.transaction && (
        <button type="button" onClick={() => onOpen(o.transaction!.id)} className="flex items-center justify-between rounded-lg bg-card px-3 py-2 text-left text-sm ring-1 ring-border hover:bg-muted">
          <span><span className="font-medium">{o.transaction.merchant}</span> · {o.transaction.category?.name ?? "—"} · {o.transaction.account?.name ?? ""}</span>
          <span className="tabular font-medium">{o.transaction.direction === "credit" ? "+" : "−"}{inr(o.transaction.amount, { decimals: true })}</span>
        </button>
      )}
    </div>
  );
}

function Simulator({ channel, source, templates, onOpen }: { channel: Kind; source?: Source; templates: Template[]; onOpen: (id: number) => void }) {
  const qc = useQueryClient();
  const refresh = useRefresh();
  const [sender, setSender] = useState("");
  const [body, setBody] = useState("");
  const [subject, setSubject] = useState("");
  const [html, setHtml] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const send = useMutation({
    mutationFn: () => post<Outcome>("/ingest/simulate", channel === "sms" ? { channel, sender, body } : { channel, sender, subject, ...(html !== null ? { html } : { body }) }),
    onSuccess: (r) => { setOutcome(r); refresh(); qc.invalidateQueries({ queryKey: ["sim-templates"] }); },
    onError: (e) => toast.error((e as Error).message),
  });
  function pick(t: Template) {
    setSelected(t.id);
    setSender(t.sender);
    setBody(t.body ?? "");
    setSubject(t.subject ?? "");
    setHtml(t.html ?? null);
    setOutcome(null);
  }
  const groups = templates.reduce<Record<string, Template[]>>((acc, t) => ((acc[t.group] ??= []).push(t), acc), {});
  const active = source?.status === "active";
  const Icon = ICON[channel];
  return (
    <section className="grid content-start gap-4 rounded-xl border border-border bg-card p-5" aria-label={channel === "sms" ? "Phone simulator" : "Mail simulator"}>
      <div>
        <h2 className="flex items-center gap-2 font-semibold"><Icon className="size-4" /> {channel === "sms" ? "Phone" : "Mailbox"} simulator</h2>
        <p className="text-sm text-muted-foreground">
          {channel === "sms" ? "Send a message as if it just arrived on your phone." : "Deliver an email as if it just reached your inbox."} It goes through exactly the same pipeline as everything else.
        </p>
      </div>
      {!active ? (
        <p className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
          Connect {channel === "sms" ? "SMS" : "email"} above to try the simulator — a paused or revoked source refuses every message, including simulated ones.
        </p>
      ) : (
        <>
          <div className="grid gap-2">
            {Object.entries(groups).map(([g, ts]) => (
              <div key={g} className="flex flex-wrap items-center gap-1.5">
                <span className="w-full text-xs font-medium text-muted-foreground">{g}</span>
                {ts.map((t) => (
                  <button key={t.id} type="button" onClick={() => pick(t)}
                    className={cn("rounded-full border px-2.5 py-1 text-xs transition-colors", selected === t.id ? "border-primary bg-secondary text-secondary-foreground" : "border-border hover:bg-muted")}>
                    {t.label}
                  </button>
                ))}
              </div>
            ))}
          </div>
          <form className="grid gap-2" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
            <label className="grid gap-1 text-sm">{channel === "sms" ? "Sender ID" : "From"}
              <Input value={sender} onChange={(e) => setSender(e.target.value)} required placeholder={channel === "sms" ? "VM-HDFCBK-S" : "Swiggy <noreply@swiggy.in>"} />
            </label>
            {channel === "email" && (
              <label className="grid gap-1 text-sm">Subject<Input value={subject} onChange={(e) => setSubject(e.target.value)} /></label>
            )}
            {channel === "email" && html !== null ? (
              <div className="grid gap-1 text-sm">
                <div className="flex items-center justify-between">Email
                  <button type="button" className="text-xs text-muted-foreground underline" onClick={() => { setBody(""); setHtml(null); }}>Write plain text instead</button>
                </div>
                <iframe title="Email preview" sandbox="" srcDoc={`<body style="font:14px system-ui;margin:12px;color:#222">${html}</body>`} className="h-56 w-full rounded-lg border border-border bg-white" />
              </div>
            ) : (
              <label className="grid gap-1 text-sm">{channel === "sms" ? "Message" : "Email text"}
                <Textarea rows={channel === "sms" ? 5 : 7} value={body} onChange={(e) => setBody(e.target.value)} required />
              </label>
            )}
            <div className="flex justify-end">
              <Button type="submit" disabled={send.isPending || !sender.trim() || (!body.trim() && !html)}>
                {send.isPending ? <LoaderCircle className="animate-spin" /> : <Send />} {channel === "sms" ? "Send SMS" : "Deliver email"}
              </Button>
            </div>
          </form>
          {outcome && <OutcomeCard o={outcome} onOpen={onOpen} />}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------

type ConsentEvent = { id: number; kind: string; event: string; purposes: string[]; notice_version: string; notice_hash: string; details: Record<string, unknown>; at: string };

function ConsentHistory() {
  const q = useQuery({ queryKey: ["sources-history"], queryFn: () => get<ConsentEvent[]>("/sources/history") });
  const EVENT: Record<string, string> = { granted: "Allowed", paused: "Paused", resumed: "Resumed", revoked: "Revoked", purposes_changed: "Purposes changed", data_deleted: "Data deleted" };
  return (
    <Card title={<span className="flex items-center gap-2"><History className="size-4" /> Consent history</span>} description="Every permission change, with the exact notice version you saw. This record can't be edited.">
      {!q.data?.length ? <p className="text-sm text-muted-foreground">No consent events yet.</p> : (
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="py-2 pr-3 font-medium">When</th><th className="py-2 pr-3 font-medium">Source</th><th className="py-2 pr-3 font-medium">Event</th>
              <th className="py-2 pr-3 font-medium">Purposes</th><th className="hidden py-2 font-medium sm:table-cell">Notice</th>
            </tr></thead>
            <tbody>
              {q.data.map((e) => (
                <tr key={e.id} className="border-b border-border last:border-0">
                  <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground tabular">{fmtDate(e.at, "d MMM yyyy, HH:mm")}</td>
                  <td className="py-2 pr-3 uppercase">{e.kind}</td>
                  <td className="py-2 pr-3">
                    {EVENT[e.event] ?? titleCase(e.event)}
                    {e.event === "data_deleted" && e.details && <span className="block text-xs text-muted-foreground">{String(e.details.messages ?? 0)} messages, {String(e.details.transactions_deleted ?? 0)} transactions</span>}
                    {e.event === "granted" && e.details?.backfill_months !== undefined && <span className="block text-xs text-muted-foreground">last {String(e.details.backfill_months)} months</span>}
                  </td>
                  <td className="py-2 pr-3 text-xs">{e.purposes.map((p) => p === "picks" ? "Smart Picks" : "Transactions").join(", ")}</td>
                  <td className="hidden py-2 font-mono text-xs text-muted-foreground sm:table-cell">{e.notice_version} · {e.notice_hash}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default function ConnectionsPage() {
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => get<{ sources: Source[] }>("/sources") });
  const templates = useQuery({ queryKey: ["sim-templates"], queryFn: () => get<Template[]>("/ingest/simulator/templates") });
  const [openId, setOpenId] = useState<number | null>(null);
  const list = sources.data?.sources ?? [];
  const byKind = (k: Kind) => list.find((s) => s.kind === k);
  return (
    <>
      <PageHeader title="Connections" description="Choose which of your messages FinPilot may read, and for what. Each source needs its own permission; uploads and manual entry always work without any." />
      {sources.isLoading ? <LoaderCircle className="size-5 animate-spin" /> : (
        <div className="grid gap-4 lg:grid-cols-2">{list.map((s) => <SourceCard key={s.kind} s={s} />)}</div>
      )}
      <div className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
        <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
        <span>Designed around the consent principles of India&apos;s DPDP Act 2023 (specific, informed, withdrawable). This is a student project, not a compliance claim. Raw message text is encrypted and deleted after 90 days; extracted details are kept.</span>
      </div>
      <h2 className="mt-8 mb-3 text-lg font-semibold">Try it live</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <Simulator channel="sms" source={byKind("sms")} templates={(templates.data ?? []).filter((t) => t.channel === "sms")} onOpen={setOpenId} />
        <Simulator channel="email" source={byKind("email")} templates={(templates.data ?? []).filter((t) => t.channel === "email")} onOpen={setOpenId} />
      </div>
      <div className="mt-8"><ConsentHistory /></div>
      <TxnDrawer id={openId} onClose={() => setOpenId(null)} />
    </>
  );
}
