"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban, CircleCheck, CircleHelp, ExternalLink, Heart, Info, LoaderCircle, PackageCheck, Pencil, PiggyBank, Plus, RefreshCw, Search, ShieldCheck,
  Target, Trash2, TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { PriceChart } from "@/components/charts/charts";
import { Card, EmptyState, Pill } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { del, get, patch, post } from "@/lib/api";
import { ago, fmtDate, inr } from "@/lib/format";
import type { AffordSnapshot, Tier, Verdict, WishItem } from "@/lib/types";
import { cn } from "@/lib/utils";

type WishlistData = { disclaimer: string; snapshot: AffordSnapshot & { forecast_low_date?: string }; items: WishItem[]; counts: Record<Tier, number> };

const TIERS: { id: Tier; label: string; icon: typeof CircleCheck; text: string }[] = [
  { id: "buy_now", label: "Buy now", icon: CircleCheck, text: "Fits your safe-to-spend and this month's wants budget, and your lowest projected balance stays above your safety buffer." },
  { id: "goal", label: "For your goals", icon: Target, text: "Linked to a savings goal: buy it from the goal once it's funded, so other plans aren't delayed." },
  { id: "save_up", label: "Save up for", icon: PiggyBank, text: "Not today without touching your buffer, but within reach if you put a little aside each month." },
  { id: "not_now", label: "Not yet", icon: Ban, text: "More than a year of your current surplus away, or your income isn't known yet." },
  { id: "needs_price", label: "Needs a price", icon: CircleHelp, text: "Add a price (or a product link FinPilot can read) to see how it fits your budget." },
];
const KEYS = [["wishlist"], ["dashboard"], ["goals"], ["insights"]];

function useInvalidate() {
  const qc = useQueryClient();
  return () => { for (const k of KEYS) qc.invalidateQueries({ queryKey: k }); };
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

function CheckPrice({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [label, setLabel] = useState("");
  const [price, setPrice] = useState("");
  const check = useMutation({ mutationFn: () => post<{ verdict: Verdict }>("/afford/check", { price: Number(price), label: label || null }) });
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) check.reset(); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Can I afford it?</DialogTitle>
          <DialogDescription>Check any price against your budget, goals and forecast — for something you saw anywhere.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); check.mutate(); }}>
          <label className="grid gap-1 text-sm">What is it? (optional)<Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. a new phone" /></label>
          <label className="grid gap-1 text-sm">Price (₹)<Input type="number" inputMode="numeric" min="1" required value={price} onChange={(e) => setPrice(e.target.value)} /></label>
          <Button type="submit" disabled={check.isPending}>{check.isPending && <LoaderCircle className="animate-spin" />} Check</Button>
        </form>
        {check.data && <VerdictBox v={check.data.verdict} />}
      </DialogContent>
    </Dialog>
  );
}

function Affordability({ s }: { s: WishlistData["snapshot"] }) {
  const parts = [
    { label: "Committed", value: s.committed, color: "var(--chart-1)" },
    { label: "Essentials", value: s.essential, color: "var(--chart-2)" },
    { label: "Goal savings", value: s.goals, color: "var(--chart-3)" },
    { label: "Free to use", value: Math.max(0, s.surplus), color: "var(--chart-4)" },
  ];
  const total = Math.max(s.income, parts.reduce((a, b) => a + b.value, 0), 1);
  return (
    <Card title="How much can I spend?" description="From your income, commitments, goals and forecast — the safety buffer is never counted as spendable.">
      <div className="grid gap-4 md:grid-cols-[220px_1fr]">
        <div>
          <div className="text-sm text-muted-foreground">Comfortable to spend this month</div>
          <div className="text-3xl font-semibold tracking-tight tabular">{inr(s.spendable)}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {s.wants_known
              ? <>wants budget left {inr(s.wants_left)} of {inr(s.wants_budget)} · safe to spend overall {inr(s.safe_to_spend)}</>
              : <>safe to spend overall · <Link href="/settings/" className="underline">add your take-home pay</Link> for a monthly wants budget</>}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {s.balance_known
              ? <Pill tone={s.emergency_ok ? "good" : "warn"}>{s.emergency_ok ? <ShieldCheck className="size-3" /> : <TriangleAlert className="size-3" />} Emergency fund {s.emergency_ok ? "on track" : "below target"}</Pill>
              : <Pill tone="warn"><TriangleAlert className="size-3" /> Balance not known yet</Pill>}
            <Pill>Buffer {inr(s.buffer)}</Pill>
          </div>
        </div>
        <div className="grid content-start gap-2">
          <div className="text-xs text-muted-foreground">
            {s.income_source === "none" ? "Monthly income not known yet — it is measured once your records cover two full months"
              : `Monthly income ${inr(s.income)}${s.income_source === "profile" ? " (the take-home pay you entered)" : ""}`}
          </div>
          <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-muted" role="img" aria-label="How your monthly income is used">
            {parts.filter((p) => p.value > 0).map((p) => <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />)}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {parts.map((p) => (
              <span key={p.label} className="inline-flex items-center gap-1.5">
                <span className="inline-block size-2.5 rounded-[3px]" style={{ background: p.color }} />
                <span className="text-muted-foreground">{p.label}</span> <span className="font-medium tabular">{inr(p.value)}</span>
              </span>
            ))}
          </div>
          <ul className="mt-1 grid gap-0.5 text-xs text-muted-foreground">{s.explain.slice(3).map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      </div>
    </Card>
  );
}

function AddItem() {
  const invalidate = useInvalidate();
  const [f, setF] = useState({ text: "", price: "", url: "", max: "" });
  const add = useMutation({
    mutationFn: () => post<{ item: WishItem; fetch: { status: string; note: string } | null }>("/wishlist", {
      text: f.text.trim() || null, url: f.url.trim() || null, price: f.price ? Number(f.price) : null, max_price: f.max ? Number(f.max) : null,
    }),
    onSuccess: (r) => {
      setF({ text: "", price: "", url: "", max: "" });
      invalidate();
      if (r.fetch?.status === "ok" && r.item.price) toast.success(`Added — ${r.item.store} lists it at ${inr(r.item.price)}. FinPilot re-checks the price daily.`);
      else if (r.fetch) toast.message(r.fetch.note || "Added. Enter the price yourself.");
      else toast.success("Added to your wishlist");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Card title="Add something you want" description="A name and a price, or paste a product link — FinPilot reads the price when the store publishes it, and tracks it daily.">
      <form className="grid gap-2 sm:grid-cols-[1fr_9rem]" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Input value={f.text} onChange={set("text")} placeholder="What is it? e.g. Running shoes" aria-label="Item" />
        <Input type="number" inputMode="numeric" min="1" value={f.price} onChange={set("price")} placeholder="Price ₹" aria-label="Price" />
        <Input value={f.url} onChange={set("url")} placeholder="Product link (optional) https://…" aria-label="Product link" inputMode="url" autoCapitalize="off" />
        <Input type="number" inputMode="numeric" min="1" value={f.max} onChange={set("max")} placeholder="I'd pay up to ₹" aria-label="Most you'd pay" />
        <Button type="submit" className="sm:col-span-2" disabled={add.isPending || (!f.text.trim() && !f.url.trim())}>
          {add.isPending ? <LoaderCircle className="animate-spin" /> : <Plus />} Add to wishlist
        </Button>
      </form>
    </Card>
  );
}

function ItemCard({ item }: { item: WishItem }) {
  const invalidate = useInvalidate();
  const [editing, setEditing] = useState(false);
  const [price, setPrice] = useState(item.price ? String(item.price) : "");
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch(`/wishlist/${item.id}`, body),
    onSuccess: (_, body) => { invalidate(); setEditing(false); if (body.bought) toast.success("Marked as bought — enjoy it!"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const refresh = useMutation({
    mutationFn: () => post<{ item: WishItem; fetch: { status: string; note: string } }>(`/wishlist/${item.id}/refresh`),
    onSuccess: (r) => { invalidate(); if (r.fetch.status === "ok") toast.success(`Current price: ${inr(r.item.price ?? 0)}`); else toast.message(r.fetch.note); },
    onError: (e) => toast.error((e as Error).message),
  });
  const goal = useMutation({
    mutationFn: () => post<{ goal_id: number; target_date: string }>(`/wishlist/${item.id}/goal`),
    onSuccess: (r) => { invalidate(); toast.success(`Saved as a goal — target ${fmtDate(r.target_date, "MMM yyyy")}`); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({ mutationFn: () => del(`/wishlist/${item.id}`), onSuccess: invalidate });
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3" data-testid="wish-item">
      <div className="flex items-start gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {item.image_url && <img src={item.image_url} alt="" className="size-14 shrink-0 rounded-lg bg-white object-contain" loading="lazy" />}
        <div className="min-w-0 flex-1">
          <div className="font-medium">{item.text}</div>
          <div className="text-xs text-muted-foreground">
            {item.price !== null ? <span className="text-sm font-semibold text-foreground tabular">{inr(item.price)}</span> : "No price yet"}
            {item.price !== null && (item.price_source === "link" ? ` · from ${item.store}${item.last_checked_at ? `, checked ${ago(item.last_checked_at)}` : ""}` : " · you entered")}
            {item.max_price ? ` · up to ${inr(item.max_price)}` : ""}
          </div>
        </div>
        {item.url && (
          <a href={item.url} target="_blank" rel="noreferrer" aria-label={`Open ${item.text} at ${item.store}`} className="grid size-10 shrink-0 place-items-center rounded-lg hover:bg-muted">
            <ExternalLink className="size-4 text-muted-foreground" />
          </a>
        )}
      </div>
      {item.history.length >= 2 && <PriceChart data={item.history} height={110} />}
      <ul className="grid gap-1 text-xs">
        {item.reasons.map((r) => <li key={r} className="flex gap-1.5"><Info className="mt-px size-3.5 shrink-0 text-primary" /><span>{r}</span></li>)}
      </ul>
      {item.fetch_status && item.fetch_status !== "ok" && item.fetch_note && item.price === null && (
        <p className="rounded-md bg-[#fefaf0] px-2 py-1.5 text-xs text-[#7a5200]">{item.fetch_note}</p>
      )}
      {editing ? (
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); update.mutate({ price: Number(price) }); }}>
          <Input type="number" inputMode="numeric" min="1" required value={price} onChange={(e) => setPrice(e.target.value)} aria-label="Price" />
          <Button type="submit" disabled={update.isPending}>Save</Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
        </form>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {(item.tier === "save_up" || item.tier === "not_now") && <Button size="sm" onClick={() => goal.mutate()} disabled={goal.isPending}><Target /> Make it a goal</Button>}
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil /> {item.price === null ? "Add price" : "Edit price"}</Button>
          {item.url && <Button size="sm" variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}>{refresh.isPending ? <LoaderCircle className="animate-spin" /> : <RefreshCw />} Check price</Button>}
          <Button size="sm" variant="outline" onClick={() => update.mutate({ bought: true })}><PackageCheck /> Bought</Button>
          <Button size="sm" variant="ghost" onClick={() => remove.mutate()} aria-label={`Remove ${item.text}`}><Trash2 /> Remove</Button>
        </div>
      )}
    </li>
  );
}

export default function WishlistPage() {
  const q = useQuery({ queryKey: ["wishlist"], queryFn: () => get<WishlistData>("/wishlist") });
  const [check, setCheck] = useState(false);
  const d = q.data;
  return (
    <>
      <PageHeader title="Wishlist" description="Things you want, checked against your real income, bills, goals and forecast — FinPilot never sells or recommends products."
        actions={<Button onClick={() => setCheck(true)}><Search /> Can I afford…?</Button>} />
      {!d ? <LoaderCircle className="size-5 animate-spin" /> : (
        <div className="grid gap-6">
          <Affordability s={d.snapshot} />
          <AddItem />
          {d.items.length === 0 ? (
            <EmptyState icon={Heart} title="Your wishlist is empty">Add something you&apos;re thinking of buying — FinPilot tells you whether it fits now, how long to save for it, or whether to wait.</EmptyState>
          ) : (
            TIERS.filter((t) => d.counts[t.id]).map((t) => (
              <section key={t.id} aria-label={t.label} className="grid gap-3">
                <div>
                  <h2 className="flex items-center gap-2 text-lg font-semibold"><t.icon className="size-4" /> {t.label} <span className="text-sm font-normal text-muted-foreground">({d.counts[t.id]})</span></h2>
                  <p className="text-sm text-muted-foreground">{t.text}</p>
                </div>
                <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {d.items.filter((i) => i.tier === t.id).map((i) => <ItemCard key={i.id} item={i} />)}
                </ul>
              </section>
            ))
          )}
          <p className="text-xs text-muted-foreground">{d.disclaimer}</p>
        </div>
      )}
      <CheckPrice open={check} onOpenChange={setCheck} />
    </>
  );
}
