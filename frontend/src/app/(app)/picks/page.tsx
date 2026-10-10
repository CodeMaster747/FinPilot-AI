"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban, Bookmark, BookmarkCheck, CircleCheck, ExternalLink, Info, LoaderCircle, PiggyBank, Plus, RefreshCw, Search, ShieldCheck, ShoppingBag, Star,
  Target, Trash2, TriangleAlert, X,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { PriceChart, Sparkline } from "@/components/charts/charts";
import { Card, EmptyState, Pill } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { del, get, patch, post } from "@/lib/api";
import { ago, fmtDate, inr } from "@/lib/format";
import { useJob } from "@/lib/hooks";
import type { AffordSnapshot, Pick, Product, Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";

type PicksData = {
  enabled: boolean; disclaimer: string; preparing?: boolean;
  last_crawl: { at: string; status: string; products: number } | null;
  snapshot: (AffordSnapshot & { forecast_low_date?: string }) | null;
  picks: Pick[];
  counts?: Record<string, number>;
};
type Stores = {
  store_url: string;
  sources: { id: number; name: string; slug: string; url: string; enabled: boolean; robots_allowed: boolean; products: number; last_crawled_at: string | null; interval_hours: number }[];
  runs: { id: number; trigger: string; status: string; started_at: string; finished_at: string | null; pages_fetched: number; products: number; prices_changed: number; skipped_robots: number; errors: number; log: string[] }[];
};

const TIERS = [
  { id: "buy_now", label: "Buy now", icon: CircleCheck, text: "Within your safe-to-spend and this month's wants budget, and your lowest projected balance stays above your safety buffer." },
  { id: "goal", label: "For your goals", icon: Target, text: "Matches something you're already saving for. Buy it from the goal once it's funded, so other plans aren't delayed." },
  { id: "save_up", label: "Save up for", icon: PiggyBank, text: "Not affordable today without touching your buffer, but within reach if you set a little aside each month." },
] as const;
const ORIGIN_LABEL: Record<string, string> = { sms: "SMS", email: "email", receipt: "receipts", csv: "statements", manual: "manual entries" };

const KEYS = [["picks"], ["picks-stores"], ["dashboard"], ["goals"], ["wishlist"]];

function Stars({ rating, count }: { rating: number; count: number }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Star className="size-3 fill-[#fab219] text-[#fab219]" aria-hidden />{rating.toFixed(1)} <span>({count.toLocaleString("en-IN")})</span>
    </span>
  );
}

function Price({ p }: { p: Product }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-lg font-semibold tabular">{inr(p.price)}</span>
      {p.mrp > p.price && <span className="text-xs text-muted-foreground line-through tabular">{inr(p.mrp)}</span>}
      {p.discount_pct > 0 && <span className="text-xs font-medium text-[var(--good-text)]">{p.discount_pct}% off</span>}
    </div>
  );
}

function ImpactLine({ impact }: { impact: Pick["impact"] }) {
  if (impact.lowest_after === undefined || impact.buffer === undefined) return null;
  return (
    <div className={cn("flex items-start gap-1.5 text-xs", impact.stays_above_buffer ? "text-muted-foreground" : "text-[#a32525]")}>
      {impact.stays_above_buffer ? <ShieldCheck className="mt-px size-3.5 shrink-0 text-[var(--good)]" /> : <TriangleAlert className="mt-px size-3.5 shrink-0" />}
      Lowest balance after buying: {inr(impact.lowest_after)} (buffer {inr(impact.buffer)})
    </div>
  );
}

function PickCard({ pick, onOpen }: { pick: Pick; onOpen: (p: Pick) => void }) {
  const qc = useQueryClient();
  const p = pick.product;
  const status = useMutation({
    mutationFn: (s: string) => post(`/picks/${pick.id}/status`, { status: s }),
    onSuccess: (_, s) => { for (const k of KEYS) qc.invalidateQueries({ queryKey: k }); if (s === "dismissed") toast.success("Hidden — it won't be suggested again"); },
  });
  const goal = useMutation({
    mutationFn: () => post<{ goal_id: number; target_date: string }>(`/picks/${pick.id}/goal`),
    onSuccess: (r) => { for (const k of KEYS) qc.invalidateQueries({ queryKey: k }); toast.success(`Added as a goal — target ${fmtDate(r.target_date, "MMM yyyy")}`); },
  });
  const saved = pick.status === "saved";
  return (
    <li className="flex flex-col overflow-hidden rounded-xl border border-border bg-card" data-testid="pick-card">
      <button type="button" className="relative block aspect-[16/9] bg-white" onClick={() => onOpen(pick)} aria-label={`Details for ${p.title}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {p.image && <img src={p.image} alt="" className="size-full object-contain p-2" loading="lazy" />}
        {saved && <Pill tone="blue" className="absolute top-2 left-2"><BookmarkCheck className="size-3" /> Saved</Pill>}
      </button>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="text-xs text-muted-foreground">{p.store} · {p.brand}</div>
        <button type="button" onClick={() => onOpen(pick)} className="line-clamp-2 text-left text-sm font-medium hover:underline">{p.title}</button>
        <Price p={p} />
        <div className="flex items-center justify-between gap-2">
          {p.rating_count > 0 && <Stars rating={p.rating} count={p.rating_count} />}
          <div className="w-24"><Sparkline data={p.history} height={28} /></div>
        </div>
        <ul className="grid gap-1 text-xs">
          {pick.reasons.filter((r) => !r.startsWith("Lowest projected")).slice(0, 3).map((r) => (
            <li key={r} className="flex gap-1.5"><CircleCheck className="mt-px size-3.5 shrink-0 text-primary" /><span>{r}</span></li>
          ))}
        </ul>
        {pick.tier === "save_up" && pick.impact.monthly ? (
          <div className="rounded-md bg-muted px-2 py-1.5 text-xs">Save <span className="font-semibold">{inr(pick.impact.monthly)}/month</span> for {pick.impact.months} month{pick.impact.months === 1 ? "" : "s"}</div>
        ) : <ImpactLine impact={pick.impact} />}
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          {pick.tier === "save_up" && <Button size="sm" onClick={() => goal.mutate()} disabled={goal.isPending}><Target /> Make it a goal</Button>}
          <Button size="sm" variant="outline" onClick={() => status.mutate(saved ? "new" : "saved")}>{saved ? <BookmarkCheck /> : <Bookmark />} {saved ? "Saved" : "Save"}</Button>
          <Button size="sm" variant="ghost" onClick={() => status.mutate("dismissed")} aria-label="Not interested"><X /> Not for me</Button>
        </div>
      </div>
    </li>
  );
}

function VerdictBox({ v }: { v: Verdict }) {
  const tone = v.tier === "buy_now" ? "bg-[#e7f5e7]" : v.tier === "save_up" ? "bg-[#fdf2d6]" : "bg-[#fbe4e4]";
  const Icon = v.tier === "buy_now" ? CircleCheck : v.tier === "save_up" ? PiggyBank : Ban;
  return (
    <div className={cn("grid gap-1 rounded-lg p-3 text-sm", tone)} role="status">
      <div className="flex items-start gap-2 font-medium"><Icon className="mt-0.5 size-4 shrink-0" />{v.text}</div>
      {v.impact && (
        <div className="pl-6 text-muted-foreground">
          Lowest projected balance (next 60 days): {inr(v.impact.lowest_before)} → <span className="font-medium text-foreground">{inr(v.impact.lowest_after)}</span> around {fmtDate(v.impact.date, "d MMM")}; your buffer is {inr(v.impact.buffer)}.
        </div>
      )}
    </div>
  );
}

function DetailDialog({ pick, onClose }: { pick: Pick | null; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["product", pick?.product.id], enabled: pick !== null,
    queryFn: () => get<{ product: Product; verdict: Verdict }>(`/picks/products/${pick!.product.id}`),
  });
  const p = q.data?.product ?? pick?.product;
  return (
    <Dialog open={pick !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        {p && (
          <>
            <DialogHeader>
              <DialogTitle>{p.title}</DialogTitle>
              <DialogDescription>{p.store} · {p.brand} · {p.category}</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 sm:grid-cols-[180px_1fr]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {p.image && <img src={p.image} alt="" className="aspect-square w-full rounded-lg border border-border bg-white object-contain p-3" />}
              <div className="grid content-start gap-2">
                <Price p={p} />
                {p.rating_count > 0 && <Stars rating={p.rating} count={p.rating_count} />}
                <div className="text-xs text-muted-foreground">30-day low {inr(p.low_30)} · 30-day median {inr(p.median_30)}</div>
                {q.data ? <VerdictBox v={q.data.verdict} /> : <LoaderCircle className="size-4 animate-spin" />}
              </div>
            </div>
            {q.data && q.data.product.history.length > 1 && <PriceChart data={q.data.product.history} />}
            {pick && (
              <div>
                <div className="mb-1 text-sm font-medium">Why it was picked for you</div>
                <ul className="grid gap-1 text-sm">{pick.reasons.map((r) => <li key={r} className="flex gap-2"><CircleCheck className="mt-0.5 size-4 shrink-0 text-primary" />{r}</li>)}</ul>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" render={<a href={p.url} target="_blank" rel="noopener noreferrer" />}><ExternalLink /> Open in {p.store}</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function CheckPrice({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [label, setLabel] = useState("");
  const [price, setPrice] = useState("");
  const check = useMutation({ mutationFn: () => post<{ verdict: Verdict }>("/picks/check", { price: Number(price), label: label || null }) });
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) check.reset(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Can I afford it?</DialogTitle>
          <DialogDescription>Check any price against your budget, goals and forecast — for something you saw anywhere.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); check.mutate(); }}>
          <label className="grid gap-1 text-sm">What is it? (optional)<Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. a new phone" /></label>
          <label className="grid gap-1 text-sm">Price (₹)<Input type="number" min="1" required value={price} onChange={(e) => setPrice(e.target.value)} /></label>
          <Button type="submit" disabled={check.isPending}>{check.isPending && <LoaderCircle className="animate-spin" />} Check</Button>
        </form>
        {check.data && <VerdictBox v={check.data.verdict} />}
      </DialogContent>
    </Dialog>
  );
}

function Affordability({ s }: { s: NonNullable<PicksData["snapshot"]> }) {
  const parts = [
    { label: "Committed", value: s.committed, color: "var(--chart-1)" },
    { label: "Essentials", value: s.essential, color: "var(--chart-2)" },
    { label: "Goal savings", value: s.goals, color: "var(--chart-3)" },
    { label: "Free to use", value: Math.max(0, s.surplus), color: "var(--chart-4)" },
  ];
  const total = Math.max(s.income, parts.reduce((a, b) => a + b.value, 0));
  const spendable = Math.min(s.safe_to_spend, s.wants_left);
  return (
    <Card title="How much can I spend?" description="Worked out from your income, commitments, goals and forecast — the buffer is never counted as spendable.">
      <div className="grid gap-4 md:grid-cols-[220px_1fr]">
        <div>
          <div className="text-sm text-muted-foreground">Comfortable to spend this month</div>
          <div className="text-3xl font-semibold tracking-tight tabular">{inr(spendable)}</div>
          <div className="mt-1 text-xs text-muted-foreground">wants budget left {inr(s.wants_left)} of {inr(s.wants_budget)} · safe to spend overall {inr(s.safe_to_spend)}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Pill tone={s.emergency_ok ? "good" : "warn"}>{s.emergency_ok ? <ShieldCheck className="size-3" /> : <TriangleAlert className="size-3" />} Emergency fund {s.emergency_ok ? "on track" : "below target"}</Pill>
            <Pill>Buffer {inr(s.buffer)}</Pill>
          </div>
        </div>
        <div className="grid content-start gap-2">
          <div className="text-xs text-muted-foreground">Typical monthly income {inr(s.income)}</div>
          <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full" role="img" aria-label="How your monthly income is used">
            {parts.filter((p) => p.value > 0).map((p) => <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label}: ${inr(p.value)}`} />)}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {parts.map((p) => (
              <span key={p.label} className="inline-flex items-center gap-1.5">
                <span className="inline-block size-2.5 rounded-[3px]" style={{ background: p.color }} />
                <span className="text-muted-foreground">{p.label}</span> <span className="font-medium tabular">{inr(p.value)}</span>
              </span>
            ))}
          </div>
          <ul className="mt-1 grid gap-0.5 text-xs text-muted-foreground">{s.explain.slice(3, 5).map((e) => <li key={e}>{e}</li>)}</ul>
          <div className="text-xs text-muted-foreground">Uses data from: {s.origins.map((o) => ORIGIN_LABEL[o] ?? o).join(", ")} — only sources you allowed for Smart Picks.</div>
          {!s.complete && (
            <div className="flex items-start gap-2 rounded-lg bg-[#fdf2d6] p-2 text-xs text-[#7a5200]">
              <TriangleAlert className="mt-px size-3.5 shrink-0" />
              <span>Your balance and forecast come from sources you haven&apos;t allowed for Smart Picks, so nothing is marked “Buy now”.
                Turn on “Also use for Smart Picks” on the <a href="/connections/" className="underline">Connections</a> page to change this.</span>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function Wishlist() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["wishlist"], queryFn: () => get<{ id: number; text: string; max_price: number | null }[]>("/wishlist") });
  const [text, setText] = useState("");
  const [max, setMax] = useState("");
  const add = useMutation({
    mutationFn: () => post("/wishlist", { text, max_price: max ? Number(max) : null }),
    onSuccess: () => { setText(""); setMax(""); qc.invalidateQueries({ queryKey: ["wishlist"] }); toast.success("Added — picks will refresh in a moment"); setTimeout(() => qc.invalidateQueries({ queryKey: ["picks"] }), 2500); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/wishlist/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["wishlist"] }); setTimeout(() => qc.invalidateQueries({ queryKey: ["picks"] }), 2500); },
  });
  return (
    <Card title="Your wishlist" description="Tell FinPilot what you're looking for; it watches the stores for options that fit your budget.">
      <ul className="mb-3 divide-y divide-border text-sm">
        {(q.data ?? []).map((w) => (
          <li key={w.id} className="flex items-center gap-2 py-1.5">
            <span className="flex-1">{w.text}</span>
            {w.max_price && <span className="text-xs text-muted-foreground tabular">up to {inr(w.max_price)}</span>}
            <button type="button" aria-label={`Remove ${w.text}`} onClick={() => remove.mutate(w.id)}><Trash2 className="size-3.5 text-muted-foreground" /></button>
          </li>
        ))}
        {q.data?.length === 0 && <li className="py-1.5 text-muted-foreground">Nothing yet.</li>}
      </ul>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Input className="min-w-40 flex-1" required minLength={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. smartwatch" aria-label="Wishlist item" />
        <Input className="w-28" type="number" min="1" value={max} onChange={(e) => setMax(e.target.value)} placeholder="Max ₹" aria-label="Maximum price" />
        <Button type="submit" variant="outline" disabled={add.isPending}><Plus /> Add</Button>
      </form>
    </Card>
  );
}

function StoresCard() {
  const q = useQuery({ queryKey: ["picks-stores"], queryFn: () => get<Stores>("/picks/stores") });
  const [jobId, setJobId] = useState<number | null>(null);
  const [openRun, setOpenRun] = useState<number | null>(null);
  const job = useJob(jobId, KEYS);
  const crawl = useMutation({ mutationFn: () => post<{ job_id: number }>("/picks/crawl"), onSuccess: (r) => setJobId(r.job_id) });
  const running = job.data && ["queued", "running"].includes(job.data.status);
  const d = q.data;
  return (
    <Card title="Stores & crawling" description="The crawler visits only the bundled demo stores, obeys robots.txt and its Crawl-delay, and runs every 6 hours."
      action={<Button size="sm" variant="outline" onClick={() => crawl.mutate()} disabled={crawl.isPending || !!running}>
        {running ? <LoaderCircle className="animate-spin" /> : <RefreshCw />} Crawl now</Button>}>
      {running && (
        <div className="mb-3 grid gap-1 text-sm" role="status">
          <div className="flex items-center gap-2 text-muted-foreground">{job.data?.message ?? "Starting…"}</div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.max(3, job.data?.progress ?? 0)}%` }} /></div>
        </div>
      )}
      {d && (
        <>
          <ul className="divide-y divide-border text-sm">
            {d.sources.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 py-2">
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="min-w-24 font-medium hover:underline">{s.name}</a>
                {s.robots_allowed ? <Pill tone="good"><CircleCheck className="size-3" /> robots.txt allows</Pill> : <Pill tone="bad"><Ban className="size-3" /> robots.txt disallows — skipped</Pill>}
                <span className="ml-auto text-xs text-muted-foreground">{s.robots_allowed ? `${s.products} products · crawled ${ago(s.last_crawled_at)}` : "never fetched"}</span>
              </li>
            ))}
          </ul>
          <div className="mt-3 text-xs font-medium text-muted-foreground">Recent crawls</div>
          <ul className="mt-1 grid gap-1 text-xs">
            {d.runs.map((r) => (
              <li key={r.id}>
                <button type="button" className="flex w-full flex-wrap items-center gap-x-2 text-left hover:underline" onClick={() => setOpenRun(openRun === r.id ? null : r.id)} aria-expanded={openRun === r.id}>
                  <span className="text-muted-foreground tabular">{fmtDate(r.started_at, "d MMM, HH:mm")}</span>
                  <span className="capitalize">{r.trigger}</span>
                  <span className="text-muted-foreground">· {r.pages_fetched} pages · {r.products} products · {r.prices_changed} price changes · {r.skipped_robots} store skipped{r.errors ? ` · ${r.errors} errors` : ""}</span>
                </button>
                {openRun === r.id && <pre className="mt-1 rounded-md bg-muted p-2 font-mono text-[11px] whitespace-pre-wrap">{r.log.join("\n")}</pre>}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

export default function PicksPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["picks"], queryFn: () => get<PicksData>("/picks"), refetchInterval: (query) => (query.state.data?.preparing ? 3000 : false) });
  const [tier, setTier] = useState<(typeof TIERS)[number]["id"]>("buy_now");
  const [detail, setDetail] = useState<Pick | null>(null);
  const [checking, setChecking] = useState(false);
  const enable = useMutation({
    mutationFn: () => patch("/auth/me", { preferences: { picks_enabled: true } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["me"] }); setTimeout(() => qc.invalidateQueries({ queryKey: ["picks"] }), 1500); },
  });
  const d = q.data;
  const shown = (d?.picks ?? []).filter((p) => p.tier === tier);
  const meta = TIERS.find((t) => t.id === tier)!;
  return (
    <>
      <PageHeader title="Smart Picks" description="Products from the bundled demo stores that match what you want and fit your finances — never at the expense of your bills, goals or safety buffer."
        actions={<Button variant="outline" onClick={() => setChecking(true)}><Search /> Can I afford…?</Button>} />
      {!d ? <LoaderCircle className="size-5 animate-spin" /> : !d.enabled ? (
        <EmptyState icon={ShoppingBag} title="Smart Picks is off" action={<Button onClick={() => enable.mutate()} disabled={enable.isPending}>Turn on Smart Picks</Button>}>
          When on, FinPilot regularly scans the demo stores for products you&apos;re likely to want and checks each one against your budget and forecast. It only uses sources you allowed for this purpose.
        </EmptyState>
      ) : (
        <div className="grid gap-4">
          {d.snapshot && <Affordability s={d.snapshot} />}
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex max-w-full overflow-x-auto rounded-lg bg-muted p-1" role="tablist" aria-label="Pick tiers">
              {TIERS.map((t) => (
                <button key={t.id} type="button" role="tab" aria-selected={tier === t.id} onClick={() => setTier(t.id)}
                  className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap", tier === t.id ? "bg-card shadow-sm" : "text-muted-foreground hover:text-foreground")}>
                  <t.icon className="size-4" /> {t.label} <span className="text-xs text-muted-foreground tabular">{d.counts?.[t.id] ?? 0}</span>
                </button>
              ))}
            </div>
            {d.last_crawl && <span className="text-xs text-muted-foreground">Prices checked {ago(d.last_crawl.at)}</span>}
          </div>
          <p className="-mt-2 text-sm text-muted-foreground">{meta.text}</p>
          {shown.length === 0 ? (
            <EmptyState icon={meta.icon} title={d.preparing ? "Looking for products…" : "Nothing in this group right now"}>
              {tier === "save_up" ? "Add something bigger to your wishlist to see a savings plan for it." : "Picks refresh after every crawl and whenever your finances change."}
            </EmptyState>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">{shown.map((p) => <PickCard key={p.id} pick={p} onOpen={setDetail} />)}</ul>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Wishlist />
            <StoresCard />
          </div>
          <p className="flex gap-2 text-xs text-muted-foreground"><Info className="mt-0.5 size-3.5 shrink-0" />{d.disclaimer} Turn Smart Picks off any time in Settings.</p>
        </div>
      )}
      <DetailDialog pick={detail} onClose={() => setDetail(null)} />
      <CheckPrice open={checking} onOpenChange={setChecking} />
    </>
  );
}
