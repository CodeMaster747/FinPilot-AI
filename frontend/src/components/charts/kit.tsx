"use client";

// Shared chart chrome following the data-viz method: thin marks, hairline recessive grid, values-first
// tooltips with line keys, legend for 2+ series, and a table view as the accessible twin of every chart.
import { useState } from "react";
import { Table2 } from "lucide-react";

import { cn } from "@/lib/utils";

export const C = {
  s1: "var(--chart-1)",
  s2: "var(--chart-2)",
  s3: "var(--chart-3)",
  grid: "var(--chart-grid)",
  axis: "var(--chart-axis)",
  muted: "var(--chart-muted)",
  ink2: "var(--chart-ink-2)",
  good: "var(--good)",
  warning: "var(--warning)",
  serious: "var(--serious)",
  critical: "var(--critical)",
};

export const axisProps = {
  tick: { fill: "var(--chart-muted)", fontSize: 12 },
  tickLine: false,
  axisLine: { stroke: "var(--chart-axis)" },
} as const;

export type TipRow = { label: string; value: string; color?: string; dashed?: boolean };

export function TooltipBox({ title, rows }: { title: string; rows: TipRow[] }) {
  return (
    <div className="min-w-40 rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <div className="mb-1 text-muted-foreground">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 py-0.5">
          {r.color && (
            <svg width="14" height="4" aria-hidden className="shrink-0">
              <line x1="0" y1="2" x2="14" y2="2" stroke={r.color} strokeWidth="2.5" strokeDasharray={r.dashed ? "3 2" : undefined} />
            </svg>
          )}
          <span className="tabular text-sm font-semibold text-foreground">{r.value}</span>
          <span className="text-muted-foreground">{r.label}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; shape?: "rect" | "line" | "dashed" | "band" }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          {it.shape === "line" || it.shape === "dashed" ? (
            <svg width="16" height="4" aria-hidden><line x1="0" y1="2" x2="16" y2="2" stroke={it.color} strokeWidth="2.5" strokeDasharray={it.shape === "dashed" ? "4 3" : undefined} /></svg>
          ) : it.shape === "band" ? (
            <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: it.color, opacity: 0.18 }} />
          ) : (
            <span className="inline-block size-2.5 rounded-[3px]" style={{ background: it.color }} />
          )}
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** Figure with title, optional legend, and a table-view toggle. */
export function ChartFrame({ title, subtitle, legend, table, children, className }: {
  title: string;
  subtitle?: React.ReactNode;
  legend?: React.ReactNode;
  table?: { columns: string[]; rows: (string | number)[][] };
  children: React.ReactNode;
  className?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className={cn("rounded-xl border border-border bg-card p-4 md:p-5", className)}>
      <figcaption className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          {subtitle && <div className="mt-0.5 text-xs text-muted-foreground">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-3">
          {legend}
          {table && (
            <button type="button" onClick={() => setShowTable((v) => !v)} aria-pressed={showTable}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">
              <Table2 className="size-3.5" /> {showTable ? "Chart" : "Table"}
            </button>
          )}
        </div>
      </figcaption>
      {showTable && table ? (
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground">{table.columns.map((c) => <th key={c} className="py-1 pr-4 font-medium">{c}</th>)}</tr></thead>
            <tbody className="tabular">
              {table.rows.map((r, i) => <tr key={i} className="border-t border-border">{r.map((v, j) => <td key={j} className="py-1 pr-4">{v}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      ) : children}
    </figure>
  );
}
