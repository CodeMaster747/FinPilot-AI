"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, CircleCheck, Info, LoaderCircle, TriangleAlert, Wallet } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/app-shell";
import { BalanceChart, HBarChart } from "@/components/charts/charts";
import { Card, EmptyState, Pill, StatTile } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { get } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import type { Projection } from "@/lib/types";

type Backtest = { model: string; label: string; mae: number; rmse: number; wape: number; folds: number; horizon_days: number; end_error: number | null };
type Forecast = {
  status: "ready" | "computing";
  model: string;
  note: string | null;
  balance_now: number;
  history: { date: string; balance: number }[];
  projection: Projection[];
  events: { date: string; name: string; amount: number; category: string; source: string }[];
  net_next_30: number;
  recurring: { merchant: string; direction: string; cadence: string; amount: number; next_date: string | null; category: string; active: boolean }[];
  generated_at: string;
  lowest_60: { amount: number; date: string; below_buffer: boolean; buffer: number };
  backtest: Backtest[];
};
type WhatIf = { lowest_before: number; lowest_after: number; lowest_after_date: string; buffer: number; stays_above_buffer: boolean; projection: Projection[] };

const ORDER = ["baseline", "baseline_schedule", "prophet_schedule"];

export default function ForecastPage() {
  const q = useQuery({
    queryKey: ["forecast"], queryFn: () => get<Forecast>("/forecast"),
    refetchInterval: (query) => (query.state.data?.status === "computing" ? 3000 : false),
  });
  const [amount, setAmount] = useState("");
  const [on, setOn] = useState("");
  const [submitted, setSubmitted] = useState<{ amount: number; on: string } | null>(null);
  const wi = useQuery({
    queryKey: ["whatif", submitted],
    queryFn: () => get<WhatIf>("/forecast/whatif", { amount: submitted!.amount, on: submitted!.on || undefined }),
    enabled: submitted !== null,
  });
  const f = q.data;
  if (!f || f.status === "computing") {
    return (
      <>
        <PageHeader title="Forecast" />
        <EmptyState icon={LoaderCircle} title="Building your forecast…">This takes a few seconds after new transactions arrive.</EmptyState>
      </>
    );
  }
  const day30 = f.projection[Math.min(29, f.projection.length - 1)];
  const bt = [...f.backtest].sort((a, b) => ORDER.indexOf(a.model) - ORDER.indexOf(b.model));
  const best = bt.reduce((a, b) => (b.mae < a.mae ? b : a), bt[0]);
  const naive = bt.find((b) => b.model === "baseline");
  const sched = bt.find((b) => b.model === "baseline_schedule");
  const prophet = bt.find((b) => b.model === "prophet_schedule");
  const upcoming = f.events.filter((e) => e.date <= (f.projection[29]?.date ?? "9999"));
  return (
    <>
      <PageHeader title="Forecast" description={`Where your balance is heading over the next 90 days, across all savings accounts. Updated ${fmtDate(f.generated_at, "d MMM, HH:mm")}.`} />
      {f.note && <div className="mb-4 flex items-start gap-2 rounded-xl border border-border bg-card p-3 text-sm"><Info className="mt-0.5 size-4 shrink-0" />{f.note}</div>}
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={Wallet} label="Balance today" value={inr(f.balance_now)} sub="savings accounts, cards excluded" />
        <StatTile label="Expected in 30 days" value={inr(day30?.p50)} sub={`likely ${inr(day30?.p10)} – ${inr(day30?.p90)}`} />
        <StatTile label="Lowest point, next 60 days" value={inr(f.lowest_60.amount)} tone={f.lowest_60.below_buffer ? "bad" : "good"}
          sub={<span className="inline-flex items-center gap-1">{f.lowest_60.below_buffer ? <TriangleAlert className="size-3" /> : <CircleCheck className="size-3" />}
            {fmtDate(f.lowest_60.date, "d MMM")} · {f.lowest_60.below_buffer ? "below" : "above"} your {inr(f.lowest_60.buffer)} buffer</span>} />
        <StatTile label="Net cash flow, next 30 days" value={inr(f.net_next_30, { sign: true })} tone={f.net_next_30 >= 0 ? "good" : "bad"} sub="expected income minus spending" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <BalanceChart history={f.history} projection={f.projection} buffer={f.lowest_60.buffer} height={320}
          title="Balance — last 120 days and the next 90" whatIf={wi.data?.projection ?? null} />
        <Card title="What if I spend…" description="See how a one-off purchase changes your lowest balance.">
          <form className="grid gap-2" onSubmit={(e) => { e.preventDefault(); if (Number(amount) > 0) setSubmitted({ amount: Number(amount), on }); }}>
            <label className="grid gap-1 text-sm">Amount (₹)<Input type="number" min="1" required value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 45000" /></label>
            <label className="grid gap-1 text-sm">On (optional)<Input type="date" value={on} onChange={(e) => setOn(e.target.value)} min={f.projection[0]?.date} max={f.projection[f.projection.length - 1]?.date} /></label>
            <div className="flex gap-2">
              <Button type="submit" disabled={wi.isFetching}>{wi.isFetching && <LoaderCircle className="animate-spin" />} Check</Button>
              {submitted && <Button type="button" variant="ghost" onClick={() => { setSubmitted(null); setAmount(""); setOn(""); }}>Clear</Button>}
            </div>
          </form>
          {wi.data && submitted && (
            <div className={`mt-3 grid gap-1 rounded-lg p-3 text-sm ${wi.data.stays_above_buffer ? "bg-[#e7f5e7]" : "bg-[#fbe4e4]"}`} role="status">
              <div className="flex items-center gap-1.5 font-medium">
                {wi.data.stays_above_buffer ? <CircleCheck className="size-4 text-[var(--good)]" /> : <TriangleAlert className="size-4 text-[var(--critical)]" />}
                {wi.data.stays_above_buffer ? "You stay above your safety buffer" : "This would take you below your safety buffer"}
              </div>
              <div className="text-muted-foreground">
                Lowest balance in the next 60 days: {inr(wi.data.lowest_before)} → <span className="font-medium text-foreground">{inr(wi.data.lowest_after)}</span> around {fmtDate(wi.data.lowest_after_date, "d MMM")} (pessimistic estimate).
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title={<span className="flex items-center gap-2"><CalendarClock className="size-4" /> Coming up in the next 30 days</span>}
          description="From your recurring payments and bill reminders. These are built into the forecast.">
          {upcoming.length === 0 ? <p className="text-sm text-muted-foreground">Nothing scheduled.</p> : (
            <ul className="divide-y divide-border text-sm">
              {upcoming.map((e, i) => (
                <li key={i} className="flex items-center gap-3 py-1.5">
                  <span className="w-14 shrink-0 text-muted-foreground tabular">{fmtDate(e.date, "d MMM")}</span>
                  <span className="min-w-0 flex-1 truncate">{e.name} <span className="text-xs text-muted-foreground">· {e.source}</span></span>
                  <span className={`tabular font-medium ${e.amount > 0 ? "text-[var(--good-text)]" : ""}`}>{inr(e.amount, { sign: true })}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="grid content-start gap-4">
          <HBarChart title="How accurate is this forecast?" valueLabel="average daily error"
            subtitle={`Tested on your own history: ${bt[0]?.folds ?? 6} rolling ${bt[0]?.horizon_days ?? 30}-day windows the model hadn't seen. Lower is better.`}
            data={bt.map((b) => ({ label: b.label, value: b.mae }))} highlight={best?.label} />
          <Card title="Backtest details">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-1.5 pr-3 font-medium">Model</th><th className="py-1.5 pr-3 text-right font-medium">MAE</th>
                  <th className="py-1.5 pr-3 text-right font-medium">RMSE</th><th className="py-1.5 pr-3 text-right font-medium">WAPE</th>
                  <th className="py-1.5 text-right font-medium">30-day balance error</th>
                </tr></thead>
                <tbody className="tabular">
                  {bt.map((b) => (
                    <tr key={b.model} className="border-b border-border last:border-0">
                      <td className="py-1.5 pr-3 font-sans">{b.label} {b.model === f.model || (f.model === "prophet" && b.model === "prophet_schedule") ? <Pill tone="blue">in use</Pill> : null}</td>
                      <td className="py-1.5 pr-3 text-right">{inr(b.mae)}</td><td className="py-1.5 pr-3 text-right">{inr(b.rmse)}</td>
                      <td className="py-1.5 pr-3 text-right">{Math.round(b.wape * 100)}%</td><td className="py-1.5 text-right">{b.end_error !== null ? inr(b.end_error) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {naive && sched && prophet && (
              <p className="mt-3 text-xs text-muted-foreground">
                Honest reading: knowing your schedule (salary, rent, EMIs, SIPs, subscriptions) cuts the daily error by {Math.round((1 - sched.mae / naive.mae) * 100)}% against a
                seasonal-naive baseline. Prophet, modelling the day-to-day spending on top, improves it by a further {Math.max(0, Math.round((1 - prophet.mae / sched.mae) * 100))}%.
                WAPE is used instead of MAPE because daily net flow often crosses zero.
              </p>
            )}
          </Card>
        </div>
      </div>

      <Card className="mt-4" title="Known schedule" description="Recurring income and payments detected from your history. The forecast adds the day-to-day spending pattern on top.">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="py-1.5 pr-3 font-medium">What</th><th className="py-1.5 pr-3 font-medium">How often</th>
              <th className="py-1.5 pr-3 font-medium">Next</th><th className="py-1.5 text-right font-medium">Amount</th>
            </tr></thead>
            <tbody>
              {f.recurring.filter((r) => r.active).map((r, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  <td className="py-1.5 pr-3">{r.merchant} <span className="text-xs text-muted-foreground">· {r.category}</span></td>
                  <td className="py-1.5 pr-3 capitalize">{r.cadence}</td>
                  <td className="py-1.5 pr-3 text-muted-foreground tabular">{fmtDate(r.next_date, "d MMM yyyy")}</td>
                  <td className={`py-1.5 text-right tabular font-medium ${r.direction === "credit" ? "text-[var(--good-text)]" : ""}`}>{r.direction === "credit" ? "+" : "−"}{inr(r.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
