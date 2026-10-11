"use client";

import { CircleCheck, CircleX, LoaderCircle } from "lucide-react";

import { useJob } from "@/lib/hooks";

type IngestResult = { total?: number; counts?: Record<string, number> };

/** One-line summary of what an ingest job did, in plain words. */
export function ingestSummary(r: IngestResult | null | undefined) {
  if (!r?.counts) return null;
  const c = r.counts;
  const parts = [
    [c.created, "new transactions"],
    [(c.duplicate ?? 0) + (c.already_imported ?? 0), "already known (linked, not double-counted)"],
    [c.transfer, "transfers between your accounts"],
    [c.enriched, "receipts added to payments"],
    [c.informational, "bills, balances & notices"],
    [c.review, "sent to review"],
    [(c.ignored ?? 0) + (c.dropped ?? 0), "OTPs, promos & non-financial messages ignored"],
  ].filter(([n]) => (n as number) > 0) as [number, string][];
  return `${r.total ?? 0} messages read: ` + parts.map(([n, t]) => `${n.toLocaleString("en-IN")} ${t}`).join(" · ");
}

export function JobProgress({ jobId, invalidate = [], label }: { jobId: number | null; invalidate?: string[][]; label?: string }) {
  const job = useJob(jobId, invalidate);
  if (jobId === null || !job.data) return null;
  const j = job.data;
  const running = j.status === "queued" || j.status === "running";
  if (running) {
    return (
      <div className="grid gap-1.5 rounded-lg bg-muted p-3 text-sm" role="status">
        <div className="flex items-center gap-2"><LoaderCircle className="size-4 animate-spin" /> {j.message || label || "Working…"}</div>
        <div className="h-1.5 overflow-hidden rounded-full bg-border">
          <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.max(4, j.progress)}%` }} />
        </div>
      </div>
    );
  }
  if (j.status === "done") {
    return (
      <div className="flex items-start gap-2 rounded-lg bg-[#e7f5e7] p-3 text-sm text-[var(--good-text)]" role="status">
        <CircleCheck className="mt-0.5 size-4 shrink-0" />
        <span>{ingestSummary(j.result as IngestResult) ?? "Done."}</span>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2 rounded-lg bg-[#fbe4e4] p-3 text-sm text-[#a32525]" role="alert">
      <CircleX className="mt-0.5 size-4 shrink-0" /> <span>{j.error || "Something went wrong."}</span>
    </div>
  );
}
