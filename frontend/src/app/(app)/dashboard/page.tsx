"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, ChevronRight, Lightbulb, MessageSquareText, Mail, ShoppingBag, Wallet, ShieldCheck, TrendingUp, Flame } from "lucide-react";

import { PageHeader } from "@/components/app-shell";
import { BalanceChart, CashflowChart, HBarChart, Meter } from "@/components/charts/charts";
import { Amount, Card, EmptyState, Pill, StatTile } from "@/components/common";
import { TxnDrawer } from "@/components/txn-drawer";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { get } from "@/lib/api";
import { ago, appHref, fmtDate, inr } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Dashboard } from "@/lib/types";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

const sevTone = (s: number) => (s >= 80 ? "bad" : s >= 60 ? "warn" : "blue") as "bad" | "warn" | "blue";

export default function DashboardPage() {
  const me = useMe();
  const [txnId, setTxnId] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => get<Dashboard>("/dashboard"),
    refetchInterval: (query) => (query.state.data?.preparing ? 3000 : false) });
  const d = q.data;
  const first = me.data?.name.split(" ")[0] ?? "";

  return (
    <>
      <PageHeader title={`${greeting()}${first ? `, ${first}` : ""}`}
        description={`Here's where your money stands today, ${fmtDate(new Date().toISOString(), "d MMMM yyyy")}.`}
        actions={<>
          <Button variant="outline" render={<Link href="/insights/" />}><MessageSquareText /> Ask the coach</Button>
          <Button render={<Link href="/picks/" />}><ShoppingBag /> Smart Picks</Button>
        </>} />

      {!d ? (
        <div className="grid gap-4 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}</div>
      ) : (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {d.sources.map((s) => (
              <Link key={s.kind} href="/connections/" className="inline-flex items-center gap-1.5 hover:text-foreground">
                {s.kind === "sms" ? <MessageSquareText className="size-3.5" /> : <Mail className="size-3.5" />}
                {s.title}: <span className={s.status === "active" ? "text-[var(--good-text)]" : ""}>{s.status.replace("_", " ")}</span>
                {s.last_ingest_at && <span>· read {ago(s.last_ingest_at)}</span>}
              </Link>
            ))}
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile icon={Wallet} label="Balance" value={inr(d.kpis.balance)}
              sub={`${d.accounts.filter((a) => a.kind !== "credit_card").length} savings accounts minus card dues`} />
            <StatTile icon={ShieldCheck} label="Safe to spend this month" value={d.kpis.safe_to_spend !== null ? inr(d.kpis.safe_to_spend) : "…"}
              sub={d.kpis.safe_to_spend_total !== null ? `Bills, goals and a ${inr(d.kpis.safe_to_spend_total ?? 0)} cushion are set aside` : "Calculating…"} />
            <StatTile icon={Flame} label="Spent this month" value={inr(d.kpis.spend_month)}
              sub={`Last month: ${inr(d.kpis.spend_last_month)} · kept ${d.kpis.savings_rate_last_month}% of income`}
              tone={d.kpis.savings_rate_last_month < 0 ? "bad" : undefined} />
            <StatTile icon={TrendingUp} label="Next 30 days" value={d.kpis.net_next_30 !== null ? inr(d.kpis.net_next_30, { sign: true }) : "…"}
              sub={d.kpis.lowest_30 ? `Lowest point ${inr(d.kpis.lowest_30.amount)} on ${fmtDate(d.kpis.lowest_30.date, "d MMM")}` : "Forecast is being prepared"}
              tone={d.kpis.net_next_30 !== null && d.kpis.net_next_30 < 0 ? "bad" : "good"} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2">
              {d.balance.projection.length ? (
                <BalanceChart history={d.balance.history} projection={d.balance.projection} />
              ) : (
                <Skeleton className="h-[340px] rounded-xl" />
              )}
            </div>
            <Card title="What needs your attention" action={<Link href="/insights/" className="text-xs text-primary hover:underline">All insights</Link>}>
              {d.insights.length === 0 ? (
                <p className="text-sm text-muted-foreground">{d.preparing ? "Insights are being written…" : "Nothing urgent. Nice."}</p>
              ) : (
                <ul className="grid gap-3">
                  {d.insights.map((i) => (
                    <li key={i.id}>
                      <Link href={appHref(i.link, "/insights/")} className="group flex gap-3">
                        <span className="mt-0.5"><Pill tone={sevTone(i.severity)}><Lightbulb className="size-3" /></Pill></span>
                        <span className="min-w-0">
                          <span className="block text-sm font-medium group-hover:underline">{i.title}</span>
                          <span className="line-clamp-2 block text-xs text-muted-foreground">{i.body}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2"><CashflowChart data={d.cashflow} /></div>
            {d.categories.length ? (
              <HBarChart title="Spending this month by category" data={d.categories.map((c) => ({ label: c.category, value: c.amount }))} />
            ) : <EmptyState title="No spending yet this month" />}
          </div>

          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
            <Card title="Due in the next 14 days" description="Recurring payments and bills found in your messages">
              {d.upcoming.length === 0 ? <p className="text-sm text-muted-foreground">Nothing scheduled.</p> : (
                <ul className="grid gap-2 text-sm">
                  {d.upcoming.slice(0, 6).map((u, i) => (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-2">
                        <CalendarClock className="size-3.5 shrink-0 text-muted-foreground" />
                        <span className="truncate">{u.name}</span>
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">{fmtDate(u.date, "d MMM")}</span>
                      <span className="w-20 shrink-0 text-right tabular">{inr(Math.abs(u.amount))}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Worth a look" description="Unusual transactions">
              {d.anomalies.length === 0 ? <p className="text-sm text-muted-foreground">Nothing unusual.</p> : (
                <ul className="grid gap-2">
                  {d.anomalies.map((a) => (
                    <li key={a.transaction.id}>
                      <button type="button" onClick={() => setTxnId(a.transaction.id)} className="flex w-full items-start gap-2 text-left">
                        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" style={{ color: a.severity === "high" ? "var(--critical)" : "var(--serious)" }} aria-label={`${a.severity} severity`} />
                        <span className="min-w-0 flex-1">
                          <span className="flex justify-between gap-2 text-sm font-medium"><span className="truncate">{a.transaction.merchant}</span>
                            <Amount value={a.transaction.amount} direction={a.transaction.direction} decimals={false} /></span>
                          <span className="line-clamp-2 block text-xs text-muted-foreground">{a.explanations[0]}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Smart Picks" description="Products that fit your budget" action={<Link href="/picks/" className="text-xs text-primary hover:underline">See all</Link>}>
              {d.picks.length === 0 ? <p className="text-sm text-muted-foreground">{d.preparing ? "Crawling the demo stores…" : "Turn on Smart Picks in Settings."}</p> : (
                <ul className="grid gap-2">
                  {d.picks.map((p) => (
                    <li key={p.id}>
                      <Link href="/picks/" className="group block">
                        <span className="flex justify-between gap-2 text-sm"><span className="truncate font-medium group-hover:underline">{p.title}</span><span className="tabular">{inr(p.price)}</span></span>
                        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Pill tone={p.tier === "buy_now" ? "good" : "blue"}>{p.tier === "buy_now" ? "Fits now" : p.tier === "goal" ? "Goal" : "Save up"}</Pill>
                          <span className="truncate">{p.reason.replace(/^Matches /, "")}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Budgets this month" action={<Link href="/budgets/" className="text-xs text-primary hover:underline">Manage</Link>}>
              {d.budgets.length === 0 ? <p className="text-sm text-muted-foreground">No budgets yet.</p> : (
                <div className="grid gap-3">
                  {d.budgets.map((b) => <Meter key={b.id} label={b.category} pct={b.pct} pace={b.pace_pct} sub={`${inr(b.spent)} of ${inr(b.budget)}`} />)}
                </div>
              )}
            </Card>
          </div>
          <Link href="/transactions/" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">See all transactions <ChevronRight className="size-4" /></Link>
        </div>
      )}
      <TxnDrawer id={txnId} onClose={() => setTxnId(null)} />
    </>
  );
}
