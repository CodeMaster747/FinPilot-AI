"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Ban, CirclePause, CirclePlay, FileUp, FlaskConical, History, LoaderCircle, ShieldCheck, Smartphone, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Card } from "@/components/common";
import { Confirm } from "@/components/confirm";
import { ConsentDialog, ICON, ImportDialog, MailboxPanel, SmsPhoneSync, StatusPill, useRefresh } from "@/components/sources";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { get, patch, post } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { isNative } from "@/lib/platform";
import type { Source } from "@/lib/types";

// ---------------------------------------------------------------------------------------------
// Source card

function ExtraSenders() {
  const me = useMe();
  const refresh = useRefresh();
  const current = (me.data?.preferences?.extra_email_domains as string[] | undefined) ?? [];
  const [value, setValue] = useState("");
  const save = useMutation({
    mutationFn: (domains: string[]) => patch("/auth/me", { preferences: { extra_email_domains: domains } }),
    onSuccess: () => { setValue(""); refresh(); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <details className="rounded-lg border border-border p-3 text-sm">
      <summary className="cursor-pointer font-medium">Also read emails from…</summary>
      <p className="mt-2 text-xs text-muted-foreground">
        FinPilot reads emails only from known banks, card issuers, shops and billers. Add the domain of a bank or shop that&apos;s missing (for example <code>mybank.co.in</code>).
      </p>
      {current.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {current.map((d) => (
            <li key={d} className="flex items-center gap-1 rounded-full bg-muted py-0.5 pr-1 pl-2.5 text-xs">
              {d}
              <button type="button" aria-label={`Remove ${d}`} className="grid size-6 place-items-center rounded-full hover:bg-background"
                onClick={() => save.mutate(current.filter((x) => x !== d))}>×</button>
            </li>
          ))}
        </ul>
      )}
      <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (value.trim()) save.mutate([...current, value.trim()]); }}>
        <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="mybank.co.in" aria-label="Sender domain" autoCapitalize="off" />
        <Button type="submit" variant="outline" disabled={save.isPending}>Add</Button>
      </form>
    </details>
  );
}

function SourceCard({ s, demo }: { s: Source; demo: boolean }) {
  const refresh = useRefresh();
  const [consent, setConsent] = useState(false);
  const [importing, setImporting] = useState(false);
  const [confirm, setConfirm] = useState<null | "revoke" | "delete">(null);
  const [justGranted, setJustGranted] = useState(false);
  const Icon = ICON[s.kind];
  const native = isNative();
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
  const c = s.counts ?? {};
  const connected = s.status === "active" || s.status === "paused";
  return (
    <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 sm:p-5" aria-label={s.title}>
      <div className="flex items-start gap-3">
        <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-secondary text-secondary-foreground"><Icon className="size-5" /></div>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{s.title}</h2>
          <p className="text-sm text-muted-foreground">
            {s.kind === "sms" ? "Bank, card, UPI and biller alerts from your phone's inbox — the most complete record of your spending." : "Bank alerts, order receipts with line items, bills, statements and subscription notices from your mailbox."}
          </p>
        </div>
        <StatusPill status={s.status} />
      </div>

      {demo && (
        <p className="flex items-start gap-2 rounded-lg bg-[#fefaf0] p-3 text-sm text-[#7a5200]">
          <FlaskConical className="mt-0.5 size-4 shrink-0" /> The demo account holds a made-up person&apos;s sample messages and can&apos;t connect real ones. Create your own account to read your SMS and email.
        </p>
      )}

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
          <div className="text-sm text-muted-foreground">Allowed {fmtDate(s.granted_at, "d MMM yyyy")} · reads the last {s.backfill_months} months and everything new</div>
        </>
      )}
      {s.status === "paused" && <p className="rounded-lg bg-[#fdf2d6] p-2 text-sm text-[#7a5200]">Paused: new messages are refused until you resume. Existing data is kept.</p>}
      {s.status === "revoked" && <p className="rounded-lg bg-muted p-2 text-sm text-muted-foreground">Permission revoked: nothing is read{s.kind === "email" ? " and the mailbox password was deleted" : ""}. Data already captured is kept until you delete it.</p>}

      {!demo && s.kind === "sms" && s.status === "active" && (native ? (
        <SmsPhoneSync source={s} autoStart={justGranted} />
      ) : (
        <div className="flex items-start gap-2 rounded-lg bg-muted p-3 text-sm">
          <Smartphone className="mt-0.5 size-4 shrink-0" />
          <span>SMS are read by the <span className="font-medium">FinPilot Android app</span>: install it on your phone, sign in with this account, and it reads your bank alerts automatically. No phone handy? Import an <span className="font-medium">SMS Backup &amp; Restore</span> file instead.</span>
        </div>
      ))}
      {!demo && s.kind === "email" && <MailboxPanel source={s} />}
      {!demo && s.kind === "email" && s.status === "active" && <ExtraSenders />}

      {!demo && (
        <div className="mt-auto flex flex-wrap gap-2">
          {(s.status === "not_connected" || s.status === "revoked") && (
            <Button onClick={() => setConsent(true)}><ShieldCheck /> {s.status === "revoked" ? "Reconnect" : "Connect"}</Button>
          )}
          {s.status === "active" && (
            <>
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
      )}

      <ConsentDialog kind={s.kind} open={consent} onOpenChange={setConsent} onGranted={() => setJustGranted(true)} />
      <ImportDialog kind={s.kind} open={importing} onOpenChange={setImporting} />
      <Confirm open={confirm === "revoke"} onOpenChange={(o) => !o && setConfirm(null)} title={`Revoke access to ${s.title}?`}
        confirmLabel="Revoke" busy={act.isPending} onConfirm={() => act.mutate("revoke")}>
        FinPilot stops reading this source immediately{s.kind === "email" ? " and deletes the stored mailbox password" : ""}. What was already captured stays until you choose “Delete data”.
        {s.kind === "sms" && native && " To also remove Android's permission, open Settings → Apps → FinPilot AI → Permissions → SMS."}
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

type ConsentEvent = { id: number; kind: string; event: string; purposes: string[]; notice_version: string; notice_hash: string; details: Record<string, unknown>; at: string };

function ConsentHistory() {
  const q = useQuery({ queryKey: ["sources-history"], queryFn: () => get<ConsentEvent[]>("/sources/history") });
  const EVENT: Record<string, string> = { granted: "Allowed", paused: "Paused", resumed: "Resumed", revoked: "Revoked", purposes_changed: "Purposes changed", data_deleted: "Data deleted" };
  return (
    <Card title={<span className="flex items-center gap-2"><History className="size-4" /> Consent history</span>} description="Every permission change, with the exact notice version you saw. This record can't be edited.">
      {!q.data?.length ? <p className="text-sm text-muted-foreground">No consent events yet.</p> : (
        <ul className="grid max-h-96 gap-2 overflow-auto">
          {q.data.map((e) => (
            <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 rounded-lg bg-muted/60 px-3 py-2 text-sm">
              <span className="font-medium">{EVENT[e.event] ?? e.event}</span>
              <span className="uppercase text-muted-foreground">{e.kind}</span>
              <span className="text-muted-foreground tabular">{fmtDate(e.at, "d MMM yyyy, HH:mm")}</span>
              {e.event === "data_deleted" && e.details && <span className="w-full text-xs text-muted-foreground">{String(e.details.messages ?? 0)} messages, {String(e.details.transactions_deleted ?? 0)} transactions</span>}
              {e.event === "granted" && e.details?.backfill_months !== undefined && <span className="w-full text-xs text-muted-foreground">last {String(e.details.backfill_months)} months</span>}
              <span className="w-full font-mono text-[11px] text-muted-foreground">notice {e.notice_version} · {e.notice_hash}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function ConnectionsPage() {
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => get<{ sources: Source[]; is_demo: boolean }>("/sources") });
  const list = sources.data?.sources ?? [];
  return (
    <>
      <PageHeader title="Connections" description="Choose which of your messages FinPilot may read. Each source needs its own permission; scanning receipts, importing statements and manual entry always work without any." />
      {sources.isLoading ? <LoaderCircle className="size-5 animate-spin" /> : (
        <div className="grid gap-4 lg:grid-cols-2">{list.map((s) => <SourceCard key={s.kind} s={s} demo={Boolean(sources.data?.is_demo)} />)}</div>
      )}
      <div className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
        <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
        <span>Designed around the consent principles of India&apos;s DPDP Act 2023 (specific, informed, withdrawable). This is a student project, not a compliance claim. Raw message text is encrypted and deleted after 90 days; extracted details are kept.</span>
      </div>
      <div className="mt-8"><ConsentHistory /></div>
    </>
  );
}
