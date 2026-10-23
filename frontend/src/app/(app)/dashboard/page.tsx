"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, ChevronRight, FileSpreadsheet, Heart, Landmark, Lightbulb, MessageSquareText, Mail, ScanLine, Wallet, ShieldCheck, TrendingUp, Flame } from "lucide-react";

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

function safeToSpendNote(k: Dashboard["kpis"]): React.ReactNode {
  if (k.safe_basis === null) return "Calculating…";
  if (k.safe_basis === "none") return <Link href="/settings/" className="underline">Add your balance or take-home pay to work this out</Link>;
  if (k.safe_basis === "wants") return "This month's wants budget left — add a balance for the full picture";
  const capped = k.wants_left !== null && k.safe_to_spend !== null && k.safe_to_spend_total !== null && k.safe_to_spend < k.safe_to_spend_total;
  return `After upcoming bills, goal savings and a ${inr(k.buffer ?? 0)} safety buffer${capped ? " · capped by this month's wants budget" : ""}${k.wants_left === null ? " · add your take-home pay for a monthly budget" : ""}`;
}

function GetStarted() {
  const steps = [
    { href: "/connections/", icon: MessageSquareText, title: "Read your bank SMS", text: "Allow SMS in the Android app — a year of transactions in a minute." },
    { href: "/connections/", icon: Mail, title: "Connect your email", text: "Bank alerts, receipts and bills from Gmail or another mailbox." },
    { href: "/settings/#accounts", icon: Landmark, title: "Add an account balance", text: "So FinPilot knows how much you have today." },
    { href: "/transactions/?import=1", icon: FileSpreadsheet, title: "Import a bank statement", text: "CSV or Excel from your bank's website." },
    { href: "/scan/", icon: ScanLine, title: "Scan a receipt", text: "Cash payments and line items." },
  ];
  return (
    <Card title="Let's bring in your money" description="FinPilot has no data for you yet. Any one of these is enough to start — your dashboard fills in as soon as it does.">
      <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {steps.map((s) => (
          <li key={s.title}>
            <Link href={s.href} className="flex h-full gap-3 rounded-lg border border-border p-3 hover:bg-muted">
              <s.icon className="mt-0.5 size-4 shrink-0 text-primary" />
              <span><span className="block text-sm font-medium">{s.title}</span><span className="block text-xs text-muted-foreground">{s.text}</span></span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

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
          <Button render={<Link href="/wishlist/" />}><Heart /> Wishlist</Button>
        </>} />

      {!d ? (
        <div className="grid gap-4 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}</div>
      ) : (
        <div className="grid gap-4">
          {!d.has_data && !me.data?.is_demo && <GetStarted />}
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
            <StatTile icon={Wallet} label="Balance" value={d.kpis.balance !== null ? inr(d.kpis.balance) : "Not known yet"}
              sub={d.kpis.balance !== null
                ? `${d.accounts.filter((a) => a.kind !== "credit_card" && a.balance !== null).length} account(s) minus card dues`
                : <Link href="/settings/#accounts" className="underline">Add your balance, or it appears with a bank SMS that shows one</Link>} />
            <StatTile icon={ShieldCheck} label="Safe to spend this month"
              value={d.kpis.safe_basis === "none" ? "Not known yet" : d.kpis.safe_to_spend !== null ? inr(d.kpis.safe_to_spend) : "…"}
              sub={safeToSpendNote(d.kpis)} />
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
            <Card title="Wishlist" description="Checked against your budget" action={<Link href="/wishlist/" className="text-xs text-primary hover:underline">See all</Link>}>
              {d.wishlist.length === 0 ? <p className="text-sm text-muted-foreground">Add things you want to buy, and FinPilot tells you when they fit.</p> : (
                <ul className="grid gap-2">
                  {d.wishlist.map((w) => (
                    <li key={w.id}>
                      <Link href="/wishlist/" className="group block">
                        <span className="flex justify-between gap-2 text-sm"><span className="truncate font-medium group-hover:underline">{w.title}</span><span className="tabular">{w.price !== null ? inr(w.price) : "—"}</span></span>
                        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Pill tone={w.tier === "buy_now" ? "good" : w.tier === "not_now" ? "bad" : "blue"}>{({ buy_now: "Fits now", goal: "Goal", save_up: "Save up", not_now: "Not yet", needs_price: "No price" } as Record<string, string>)[w.tier] ?? w.tier}</Pill>
                          <span className="truncate">{w.reason}</span>
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
