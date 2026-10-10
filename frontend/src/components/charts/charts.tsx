"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, CheckCircle2, CircleAlert } from "lucide-react";

import { C, ChartFrame, Legend, TooltipBox, axisProps } from "@/components/charts/kit";
import { fmtDate, inr, inrCompact } from "@/lib/format";
import type { Projection } from "@/lib/types";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ balance: actual + forecast band */
type BalRow = { date: string; actual?: number; p50?: number; band?: [number, number] };

export function BalanceChart({ history, projection, buffer, height = 280, title = "Balance — last 90 days and next 60", whatIf }: {
  history: { date: string; balance: number }[];
  projection: Projection[];
  buffer?: number;
  height?: number;
  title?: string;
  whatIf?: Projection[] | null;
}) {
  const rows: BalRow[] = history.map((h) => ({ date: h.date, actual: h.balance }));
  if (rows.length && projection.length) {
    const last = rows[rows.length - 1];
    last.p50 = last.actual;
    last.band = [last.actual!, last.actual!];
  }
  const wi = new Map((whatIf ?? []).map((p) => [p.date, p.p50]));
  for (const p of projection) rows.push({ date: p.date, p50: p.p50, band: [p.p10, p.p90], ...(whatIf ? { wi: wi.get(p.date) } : {}) } as BalRow);
  const today = history.length ? history[history.length - 1].date : undefined;
  const lowest = Math.min(...history.map((h) => h.balance), ...projection.map((p) => p.p10), ...(whatIf ?? []).map((p) => p.p10));
  const bufferVisible = buffer !== undefined && buffer >= lowest * 0.6;
  const legend = [
    { label: "Balance", color: C.s1, shape: "line" as const },
    { label: "Projected", color: C.s1, shape: "dashed" as const },
    { label: "Likely range (80%)", color: C.s1, shape: "band" as const },
    ...(whatIf ? [{ label: "If you buy it today", color: C.s2, shape: "dashed" as const }] : []),
  ];
  return (
    <ChartFrame title={title} legend={<Legend items={legend} />}
      subtitle={buffer === undefined ? undefined : bufferVisible ? `Dashed red line: your safety buffer of ${inr(buffer)}`
        : `Your safety buffer of ${inr(buffer)} is well below this range`}
      table={{ columns: ["Date", "Balance", "Projected", "Low", "High"],
        rows: rows.map((r) => [fmtDate(r.date, "d MMM"), r.actual !== undefined ? inr(r.actual) : "", r.p50 !== undefined && r.actual === undefined ? inr(r.p50) : "",
          r.band && r.actual === undefined ? inr(r.band[0]) : "", r.band && r.actual === undefined ? inr(r.band[1]) : ""]) }}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="date" {...axisProps} tickFormatter={(d) => fmtDate(d, "d MMM")} minTickGap={40} />
            <YAxis {...axisProps} axisLine={false} width={64} tickFormatter={(v) => inrCompact(v)} domain={["auto", "auto"]} />
            <Tooltip cursor={{ stroke: C.axis, strokeWidth: 1 }} content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as BalRow & { wi?: number };
              const rows = r.actual !== undefined
                ? [{ label: "balance", value: inr(r.actual), color: C.s1 }]
                : [{ label: "projected", value: inr(r.p50!), color: C.s1, dashed: true },
                   ...(r.band ? [{ label: "likely range", value: `${inrCompact(r.band[0])} – ${inrCompact(r.band[1])}` }] : []),
                   ...(r.wi !== undefined ? [{ label: "if bought today", value: inr(r.wi), color: C.s2, dashed: true }] : [])];
              return <TooltipBox title={fmtDate(String(label), "EEE, d MMM yyyy")} rows={rows} />;
            }} />
            <Area dataKey="band" stroke="none" fill={C.s1} fillOpacity={0.12} isAnimationActive={false} />
            <Line dataKey="actual" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} strokeLinecap="round" />
            <Line dataKey="p50" stroke={C.s1} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            {whatIf && <Line dataKey="wi" stroke={C.s2} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />}
            {bufferVisible && <ReferenceLine y={buffer} stroke={C.serious} strokeDasharray="4 4" strokeWidth={1} ifOverflow="extendDomain" />}
            {today && <ReferenceLine x={today} stroke={C.axis} strokeWidth={1} label={{ value: "Today", position: "insideTopLeft", fill: "var(--chart-muted)", fontSize: 11 }} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ monthly income vs spending */
export function CashflowChart({ data, height = 260 }: { data: { month: string; income: number; spend: number; savings_rate: number }[]; height?: number }) {
  return (
    <ChartFrame title="Income and spending by month" subtitle="Transfers between your own accounts and card bill payments are excluded"
      legend={<Legend items={[{ label: "Income", color: C.s1 }, { label: "Spending", color: C.s2 }]} />}
      table={{ columns: ["Month", "Income", "Spending", "Kept"], rows: data.map((d) => [fmtDate(d.month, "MMM yyyy"), inr(d.income), inr(d.spend), `${d.savings_rate}%`]) }}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 4 }} barGap={2} barCategoryGap="28%">
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="month" {...axisProps} tickFormatter={(d) => fmtDate(d, "MMM")} />
            <YAxis {...axisProps} axisLine={false} width={56} tickFormatter={(v) => inrCompact(v)} />
            <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.6 }} content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as { income: number; spend: number; savings_rate: number };
              return <TooltipBox title={fmtDate(String(label), "MMMM yyyy")} rows={[
                { label: "income", value: inr(r.income), color: C.s1 }, { label: "spending", value: inr(r.spend), color: C.s2 },
                { label: "of income kept", value: `${r.savings_rate}%` }]} />;
            }} />
            <Bar dataKey="income" fill={C.s1} maxBarSize={18} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="spend" fill={C.s2} maxBarSize={18} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ one-hue horizontal bars */
export function HBarChart({ title, subtitle, data, valueLabel = "amount", format = inr, highlight, height }: {
  title: string;
  subtitle?: string;
  data: { label: string; value: number }[];
  valueLabel?: string;
  format?: (v: number) => string;
  highlight?: string;
  height?: number;
}) {
  const h = height ?? Math.max(120, data.length * 34 + 16);
  return (
    <ChartFrame title={title} subtitle={subtitle} table={{ columns: ["", valueLabel], rows: data.map((d) => [d.label, format(d.value)]) }}>
      <div style={{ height: h }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 72, bottom: 0, left: 0 }} barCategoryGap={8}>
            <XAxis type="number" hide domain={[0, "dataMax"]} />
            <YAxis type="category" dataKey="label" width={130} tick={{ fill: "var(--chart-ink-2)", fontSize: 12 }} tickLine={false} axisLine={false} />
            <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.6 }} content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as { label: string; value: number };
              return <TooltipBox title={r.label} rows={[{ label: valueLabel, value: format(r.value) }]} />;
            }} />
            <Bar dataKey="value" maxBarSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}
              shape={(props: unknown) => {
                const p = props as { x: number; y: number; width: number; height: number; payload: { label: string } };
                const fill = highlight && p.payload.label !== highlight ? "var(--chart-axis)" : C.s1;
                const r = Math.min(4, p.height / 2, p.width / 2);
                return <path d={`M${p.x},${p.y} h${Math.max(0, p.width - r)} a${r},${r} 0 0 1 ${r},${r} v${Math.max(0, p.height - 2 * r)} a${r},${r} 0 0 1 -${r},${r} h-${Math.max(0, p.width - r)} z`} fill={fill} />;
              }}>
              <LabelList dataKey="value" position="right" formatter={(v: unknown) => format(Number(v))} style={{ fill: "var(--chart-ink-2)", fontSize: 12 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------ sparkline */
export function Sparkline({ data, height = 36, accentLast = true }: { data: { date: string; price: number }[]; height?: number; accentLast?: boolean }) {
  if (!data.length) return null;
  const last = data[data.length - 1];
  return (
    <div style={{ height }} aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 6, bottom: 4, left: 2 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line dataKey="price" stroke="var(--chart-axis)" strokeWidth={1.5} dot={false} isAnimationActive={false}
            activeDot={false} />
          {accentLast && (
            <Line dataKey={(d: { date: string; price: number }) => (d.date === last.date ? d.price : null)} stroke="none"
              dot={{ r: 3.5, fill: C.s1, stroke: "var(--card)", strokeWidth: 2 }} isAnimationActive={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------------------------ price history (product detail) */
export function PriceChart({ data, height = 200 }: { data: { date: string; price: number }[]; height?: number }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="date" {...axisProps} tickFormatter={(d) => fmtDate(d, "d MMM")} minTickGap={36} />
          <YAxis {...axisProps} axisLine={false} width={60} tickFormatter={(v) => inrCompact(v)} domain={["auto", "auto"]} />
          <Tooltip content={({ active, payload, label }) => active && payload?.length
            ? <TooltipBox title={fmtDate(String(label), "d MMM yyyy")} rows={[{ label: "price", value: inr(Number(payload[0].value)), color: C.s1 }]} /> : null} />
          <Line dataKey="price" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} type="stepAfter" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------------------------ small chart for coach answers */
export function MiniChart({ chart }: { chart: { type: "bar" | "line" | "progress"; title: string; data: { label: string; value: number; low?: number; high?: number }[] } }) {
  if (chart.type === "progress") {
    return (
      <div className="mt-3 grid gap-2">
        {chart.data.map((d) => <Meter key={d.label} label={d.label} pct={d.value} />)}
      </div>
    );
  }
  if (chart.type === "line") {
    const rows = chart.data.map((d) => ({ ...d, band: d.low !== undefined ? [d.low, d.high] : undefined }));
    return (
      <div className="mt-3 h-40 rounded-lg border border-border bg-card p-2">
        <div className="px-1 text-xs text-muted-foreground">{chart.title}</div>
        <ResponsiveContainer width="100%" height="88%">
          <ComposedChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="label" {...axisProps} minTickGap={30} />
            <YAxis {...axisProps} axisLine={false} width={52} tickFormatter={(v) => inrCompact(v)} domain={["auto", "auto"]} />
            <Tooltip content={({ active, payload, label }) => active && payload?.length
              ? <TooltipBox title={String(label)} rows={[{ label: "projected", value: inr(Number((payload[0].payload as { value: number }).value)), color: C.s1 }]} /> : null} />
            <Area dataKey="band" stroke="none" fill={C.s1} fillOpacity={0.12} isAnimationActive={false} />
            <Line dataKey="value" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-lg border border-border bg-card p-2" style={{ height: Math.max(110, chart.data.length * 30 + 30) }}>
      <div className="px-1 text-xs text-muted-foreground">{chart.title}</div>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart data={chart.data} layout="vertical" margin={{ top: 4, right: 64, bottom: 0, left: 0 }} barCategoryGap={6}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={110} tick={{ fill: "var(--chart-ink-2)", fontSize: 12 }} tickLine={false} axisLine={false} />
          <Bar dataKey="value" fill={C.s1} maxBarSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            <LabelList dataKey="value" position="right" formatter={(v: unknown) => inrCompact(Number(v))} style={{ fill: "var(--chart-ink-2)", fontSize: 12 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------------------------ meter: budgets, goals, limits */
export function Meter({ label, pct, sub, pace }: { label: string; pct: number; sub?: React.ReactNode; pace?: number }) {
  const status = pct > 100 ? "critical" : pct >= 85 ? "warning" : "ok";
  const fill = status === "critical" ? C.critical : status === "warning" ? C.warning : C.s1;
  const track = status === "critical" ? "#f6dada" : status === "warning" ? "#fdf0cf" : "#dbe8f9";
  const Icon = status === "critical" ? CircleAlert : status === "warning" ? AlertTriangle : CheckCircle2;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-sm">
        <span className="flex min-w-0 items-center gap-1.5 truncate font-medium">{label}</span>
        <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground tabular">
          <Icon className={cn("size-3.5", status === "ok" && "text-[var(--chart-1)]")} style={status !== "ok" ? { color: fill } : undefined} aria-hidden />
          {Math.round(pct)}%{status === "critical" ? " — over" : status === "warning" ? " — close" : ""}
        </span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full" style={{ background: track }} role="meter" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(2, pct))}%`, background: fill }} />
        {pace !== undefined && <div className="absolute top-0 h-full w-0.5 bg-foreground/40" style={{ left: `${Math.min(100, pace)}%` }} title="Where you'd be at an even pace" />}
      </div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}
