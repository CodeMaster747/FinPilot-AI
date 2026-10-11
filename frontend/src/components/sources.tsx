"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CircleCheck, CirclePause, Download, FileUp, LoaderCircle, Mail, MessageSquareText, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { NativeSelect, Pill } from "@/components/common";
import { JobProgress } from "@/components/job-progress";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { api, get, post } from "@/lib/api";
import type { Notice, Source } from "@/lib/types";

export type Kind = "sms" | "email";
export const ICON = { sms: MessageSquareText, email: Mail };
export const REFRESH = [["sources"], ["sources-history"], ["transactions"], ["dashboard"], ["review-counts"], ["review"], ["me"]];

export function useRefresh() {
  const qc = useQueryClient();
  return () => { for (const k of REFRESH) qc.invalidateQueries({ queryKey: k }); };
}

export function StatusPill({ status }: { status: Source["status"] }) {
  if (status === "active") return <Pill tone="good"><CircleCheck className="size-3" /> Connected</Pill>;
  if (status === "paused") return <Pill tone="warn"><CirclePause className="size-3" /> Paused</Pill>;
  if (status === "revoked") return <Pill tone="bad"><Ban className="size-3" /> Revoked</Pill>;
  return <Pill>Not connected</Pill>;
}

// ---------------------------------------------------------------------------------------------
// Consent dialog: itemised notice, two separate unticked purposes, backfill window

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
  const [purposes, setPurposes] = useState<Record<string, boolean>>({ transactions: false, picks: false });
  const [backfill, setBackfill] = useState("12");
  const grant = useMutation({
    mutationFn: () => post<Source>(`/sources/${kind}/grant`, { purposes: Object.keys(purposes).filter((p) => purposes[p]), backfill_months: Number(backfill) }),
    onSuccess: () => { toast.success(`${notice.data?.title ?? kind} connected`); refresh(); onOpenChange(false); onGranted?.(); },
    onError: (e) => toast.error((e as Error).message),
  });
  const n = notice.data;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Allow FinPilot to read your {kind === "sms" ? "bank & payment SMS" : "receipts & bank emails"}?</DialogTitle>
          <DialogDescription>Nothing is read until you agree. You can pause, revoke or delete this data at any time from this page.</DialogDescription>
        </DialogHeader>
        {!n ? <LoaderCircle className="mx-auto size-5 animate-spin" /> : (
          <div className="grid gap-4">
            <NoticeSection title="What is read" items={n.reads} />
            <NoticeSection title="What is never read" items={n.never_reads} tone="no" />
            <NoticeSection title="What is stored" items={n.stores} />
            <NoticeSection title="FinPilot will never" items={n.never} tone="no" />
            <fieldset className="grid gap-2 rounded-lg border border-border p-3">
              <legend className="px-1 text-sm font-medium">Choose what this data may be used for</legend>
              {Object.entries(n.purposes).map(([key, text]) => (
                <label key={key} className="flex items-start gap-2 text-sm">
                  <Checkbox className="mt-0.5" checked={purposes[key]} onCheckedChange={(v) => setPurposes({ ...purposes, [key]: Boolean(v) })} aria-label={text} />
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
            <p className="text-xs text-muted-foreground">Notice version {n.version} · fingerprint {n.hash.slice(0, 12)} — recorded with your choice in the consent history.</p>
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

type SampleFile = { name: string; label: string; url: string; kind: string };

export function ImportDialog({ kind, open, onOpenChange }: { kind: Kind; open: boolean; onOpenChange: (o: boolean) => void }) {
  const refresh = useRefresh();
  const [jobId, setJobId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [paste, setPaste] = useState("");
  const samples = useQuery({ queryKey: ["samples"], queryFn: () => get<SampleFile[]>("/samples"), enabled: open });

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
  async function importSample(s: SampleFile) {
    const res = await fetch(s.url, { credentials: "same-origin" });
    await upload(new File([await res.blob()], s.name));
  }
  const accept = kind === "sms" ? ".xml,.csv,.txt" : ".eml,.mbox,.txt";
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setJobId(null); setPaste(""); } }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import {kind === "sms" ? "SMS" : "emails"} from a file</DialogTitle>
          <DialogDescription>
            {kind === "sms"
              ? "An Android “SMS Backup & Restore” XML file, a CSV export (date, sender, message), or messages pasted as text."
              : "A single email (.eml) or a mailbox archive (.mbox) — for example from Google Takeout."}{" "}
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
          {(samples.data ?? []).filter((s) => s.kind === kind).length > 0 && (
            <div className="grid gap-1.5 rounded-lg bg-muted p-3">
              <div className="text-xs font-medium text-muted-foreground">No file handy? Try a sample generated from the demo persona:</div>
              {samples.data!.filter((s) => s.kind === kind).map((s) => (
                <div key={s.name} className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1">{s.label}</span>
                  <Button size="sm" variant="ghost" render={<a href={s.url} download={s.name} />}><Download /> Download</Button>
                  <Button size="sm" variant="outline" onClick={() => importSample(s)} disabled={busy}>Import it</Button>
                </div>
              ))}
            </div>
          )}
          <JobProgress jobId={jobId} invalidate={REFRESH} label="Reading your file" />
        </div>
        <DialogFooter><Button variant="outline" onClick={() => { onOpenChange(false); refresh(); }}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
