"use client";

import { Fragment } from "react";

import { inr } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Field = { value: unknown; confidence: number; span?: [number, number] | null };

export const FIELD_LABELS: Record<string, string> = {
  amount: "Amount", direction: "Direction", payee: "Paid to / from", merchant: "Merchant", mask: "Account", account_no: "Account",
  ref: "Reference", date: "Date", time: "Time", balance: "Balance", available_limit: "Available limit", vpa: "UPI ID",
  due_date: "Due date", min: "Minimum due", order_id: "Order no.", items: "Line items", total: "Total", service: "Service",
  old_amount: "Old price", effective_date: "From", notice: "Notice", policy: "Policy", scheme: "Fund",
};

// Highlight colours for the extracted spans (light tints; text stays in the ink colour).
const TINTS: Record<string, string> = {
  amount: "bg-[#d7e7fb]", payee: "bg-[#fde3d6]", merchant: "bg-[#fde3d6]", mask: "bg-[#d6f1e5]", account_no: "bg-[#d6f1e5]",
  ref: "bg-[#ece4fb]", date: "bg-[#fdf2d6]", time: "bg-[#fdf2d6]", balance: "bg-[#e3e8ee]", vpa: "bg-[#fde3d6]", due_date: "bg-[#fdf2d6]",
};

export function fieldValue(key: string, f: Field): string {
  const v = f.value;
  if (v === null || v === undefined) return "—";
  if (key === "items" && Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
  if (["amount", "balance", "available_limit", "min", "total", "old_amount"].includes(key)) return inr(Number(v), { decimals: true });
  if (key === "direction") return v === "debit" ? "Money out" : "Money in";
  if (key === "mask" || key === "account_no") return `XX${String(v).slice(-4)}`;
  return String(v);
}

/** The original message with each extracted value highlighted where it was found. */
export function HighlightedText({ text, fields, className }: { text: string; fields?: Record<string, Field> | null; className?: string }) {
  const spans = Object.entries(fields ?? {})
    .filter(([, f]) => f.span && f.span[0] >= 0 && f.span[1] <= text.length && f.span[1] > f.span[0])
    .map(([k, f]) => ({ key: k, start: f.span![0], end: f.span![1] }))
    .sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let pos = 0;
  for (const s of spans) {
    if (s.start < pos) continue; // overlapping span — keep the first
    if (s.start > pos) parts.push(<Fragment key={`t${pos}`}>{text.slice(pos, s.start)}</Fragment>);
    parts.push(
      <mark key={`m${s.start}`} title={FIELD_LABELS[s.key] ?? s.key} className={cn("rounded-sm px-0.5 text-foreground", TINTS[s.key] ?? "bg-[#e3e8ee]")}>
        {text.slice(s.start, s.end)}
      </mark>,
    );
    pos = s.end;
  }
  if (pos < text.length) parts.push(<Fragment key="tail">{text.slice(pos)}</Fragment>);
  return <p className={cn("text-sm leading-relaxed break-words whitespace-pre-wrap", className)}>{parts}</p>;
}

/** Extracted fields as a compact definition list, with confidence. */
export function FieldList({ fields, className }: { fields?: Record<string, Field> | null; className?: string }) {
  const entries = Object.entries(fields ?? {}).filter(([k]) => k !== "notice");
  if (!entries.length) return <p className="text-xs text-muted-foreground">No fields extracted.</p>;
  return (
    <dl className={cn("grid grid-cols-[auto_1fr_auto] items-baseline gap-x-3 gap-y-1 text-sm", className)}>
      {entries.map(([k, f]) => (
        <Fragment key={k}>
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            <span className={cn("inline-block size-2.5 rounded-sm", TINTS[k] ?? "bg-[#e3e8ee]")} aria-hidden />
            {FIELD_LABELS[k] ?? k}
          </dt>
          <dd className="min-w-0 truncate font-medium">{fieldValue(k, f)}</dd>
          <dd className={cn("text-right text-xs tabular", f.confidence < 0.8 ? "text-[#7a5200]" : "text-muted-foreground")}>
            {Math.round(f.confidence * 100)}%
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}
