"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Check, LoaderCircle, Pencil, PiggyBank, Plus, Target, Trash2, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Meter } from "@/components/charts/charts";
import { Card, CategoryIcon, EmptyState, NativeSelect } from "@/components/common";
import { Confirm } from "@/components/confirm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { del, get, patch, post, put } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import type { Category } from "@/lib/types";

type Budget = { id: number; category: string; category_id: number; icon: string; budget: number; spent: number; pct: number; pace_pct: number; over_pace: boolean; over: boolean };
type Goal = { id: number; name: string; target: number; saved: number; target_date: string; pct: number; remaining: number; months_left: number; monthly_needed: number; product_id: number | null };

const KEYS = [["budgets"], ["goals"], ["dashboard"], ["picks"], ["insights"]];

function useInvalidate() {
  const qc = useQueryClient();
  return () => { for (const k of KEYS) qc.invalidateQueries({ queryKey: k }); };
}

function BudgetRow({ b }: { b: Budget }) {
  const invalidate = useInvalidate();
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(String(b.budget));
  const [confirm, setConfirm] = useState(false);
  const save = useMutation({
    mutationFn: () => put("/budgets", { category_id: b.category_id, amount: Number(amount) }),
    onSuccess: () => { setEditing(false); invalidate(); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({ mutationFn: () => del(`/budgets/${b.id}`), onSuccess: () => { setConfirm(false); invalidate(); } });
  const left = b.budget - b.spent;
  return (
    <li className="grid gap-2 py-3">
      <div className="flex items-start gap-2">
        <CategoryIcon icon={b.icon} className="mt-0.5 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <Meter label={b.category} pct={b.pct} pace={b.pace_pct}
            sub={<>{inr(b.spent)} of {inr(b.budget)} · {left >= 0 ? `${inr(left)} left` : `${inr(-left)} over`}{b.over_pace && !b.over ? " · ahead of pace" : ""}</>} />
        </div>
        {!editing && (
          <div className="flex shrink-0 gap-0.5">
            <Button size="icon-sm" variant="ghost" aria-label={`Edit ${b.category} budget`} onClick={() => setEditing(true)}><Pencil /></Button>
            <Button size="icon-sm" variant="ghost" aria-label={`Remove ${b.category} budget`} onClick={() => setConfirm(true)}><Trash2 /></Button>
          </div>
        )}
      </div>
      {editing && (
        <form className="flex items-center justify-end gap-1 pl-6" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <span className="mr-1 text-xs text-muted-foreground">Monthly limit (₹)</span>
          <Input type="number" min="1" required value={amount} onChange={(e) => setAmount(e.target.value)} className="h-7 w-28" aria-label={`Budget for ${b.category}`} autoFocus />
          <Button size="icon-sm" type="submit" aria-label="Save" disabled={save.isPending}><Check /></Button>
          <Button size="icon-sm" type="button" variant="ghost" aria-label="Cancel" onClick={() => setEditing(false)}><X /></Button>
        </form>
      )}
      <Confirm open={confirm} onOpenChange={setConfirm} title={`Remove the ${b.category} budget?`} confirmLabel="Remove" destructive busy={remove.isPending} onConfirm={() => remove.mutate()}>
        Your transactions are not affected — only the monthly limit is removed.
      </Confirm>
    </li>
  );
}

function AddBudget({ cats, taken }: { cats: Category[]; taken: Set<number> }) {
  const invalidate = useInvalidate();
  const [category, setCategory] = useState("");
  const [amount, setAmount] = useState("");
  const add = useMutation({
    mutationFn: () => put("/budgets", { category_id: Number(category), amount: Number(amount) }),
    onSuccess: () => { setCategory(""); setAmount(""); invalidate(); toast.success("Budget added"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const options = cats.filter((c) => c.kind === "expense" && !taken.has(c.id));
  return (
    <form className="flex flex-wrap items-end gap-2 border-t border-border pt-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
      <label className="grid gap-1 text-sm">Category
        <NativeSelect required value={category} onChange={(e) => setCategory(e.target.value)} className="h-8 w-48">
          <option value="" disabled>Choose…</option>
          {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </NativeSelect>
      </label>
      <label className="grid gap-1 text-sm">Monthly limit (₹)<Input type="number" min="1" required value={amount} onChange={(e) => setAmount(e.target.value)} className="w-32" /></label>
      <Button type="submit" variant="outline" disabled={add.isPending}>{add.isPending ? <LoaderCircle className="animate-spin" /> : <Plus />} Add budget</Button>
    </form>
  );
}

function GoalCard({ g }: { g: Goal }) {
  const invalidate = useInvalidate();
  const [add, setAdd] = useState("");
  const [confirm, setConfirm] = useState(false);
  const deposit = useMutation({
    mutationFn: () => patch<{ status: string }>(`/goals/${g.id}`, { add: Number(add) }),
    onSuccess: (r) => { setAdd(""); invalidate(); toast.success(r.status === "achieved" ? `🎉 “${g.name}” is fully funded!` : `Added ${inr(Number(add))} to “${g.name}”`); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({ mutationFn: () => del(`/goals/${g.id}`), onSuccess: () => { setConfirm(false); invalidate(); } });
  const pct = Math.min(100, g.pct);
  return (
    <li className="grid gap-3 rounded-xl border border-border p-4">
      <div className="flex items-start gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-secondary text-secondary-foreground"><Target className="size-4" /></div>
        <div className="min-w-0 flex-1">
          <div className="font-medium">{g.name}</div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground"><CalendarDays className="size-3" /> by {fmtDate(g.target_date, "MMM yyyy")} · {g.months_left} month{g.months_left === 1 ? "" : "s"} left</div>
        </div>
        <button type="button" aria-label={`Delete ${g.name}`} className="rounded p-1 text-muted-foreground hover:bg-muted" onClick={() => setConfirm(true)}><Trash2 className="size-4" /></button>
      </div>
      <div>
        <div className="mb-1 flex items-baseline justify-between text-sm">
          <span><span className="font-semibold tabular">{inr(g.saved)}</span> <span className="text-muted-foreground">of {inr(g.target)}</span></span>
          <span className="text-xs text-muted-foreground tabular">{Math.round(g.pct)}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[#dbe8f9]" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={`${g.name} progress`}>
          <div className="h-full rounded-full bg-[var(--chart-1)]" style={{ width: `${Math.max(2, pct)}%` }} />
        </div>
        <div className="mt-1 text-xs text-muted-foreground">Put aside {inr(g.monthly_needed)}/month to get there on time.</div>
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); deposit.mutate(); }}>
        <Input type="number" min="1" required value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Amount (₹)" aria-label={`Add money to ${g.name}`} className="h-8" />
        <Button type="submit" size="sm" variant="outline" disabled={deposit.isPending}><PiggyBank /> Add money</Button>
      </form>
      <Confirm open={confirm} onOpenChange={setConfirm} title={`Delete “${g.name}”?`} confirmLabel="Delete goal" destructive busy={remove.isPending} onConfirm={() => remove.mutate()}>
        The goal and its saved amount are removed from FinPilot. No money moves — this only affects your plan.
      </Confirm>
    </li>
  );
}

function NewGoal() {
  const invalidate = useInvalidate();
  const nextYear = new Date();
  nextYear.setFullYear(nextYear.getFullYear() + 1);
  const [f, setF] = useState({ name: "", target: "", saved: "", target_date: nextYear.toISOString().slice(0, 10) });
  const create = useMutation({
    mutationFn: () => post("/goals", { name: f.name, target: Number(f.target), saved: f.saved ? Number(f.saved) : 0, target_date: f.target_date }),
    onSuccess: () => { setF({ ...f, name: "", target: "", saved: "" }); invalidate(); toast.success("Goal created"); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <form className="grid gap-2 border-t border-border pt-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <label className="grid gap-1 text-sm sm:col-span-2">What are you saving for?<Input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Emergency fund, new phone" /></label>
      <label className="grid gap-1 text-sm">Target (₹)<Input type="number" min="1" required value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} /></label>
      <label className="grid gap-1 text-sm">Already saved (₹)<Input type="number" min="0" value={f.saved} onChange={(e) => setF({ ...f, saved: e.target.value })} /></label>
      <label className="grid gap-1 text-sm">By<Input type="date" required value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} /></label>
      <div className="flex items-end"><Button type="submit" variant="outline" disabled={create.isPending}>{create.isPending ? <LoaderCircle className="animate-spin" /> : <Plus />} Create goal</Button></div>
    </form>
  );
}

export default function BudgetsPage() {
  const budgets = useQuery({ queryKey: ["budgets"], queryFn: () => get<Budget[]>("/budgets") });
  const goals = useQuery({ queryKey: ["goals"], queryFn: () => get<Goal[]>("/goals") });
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/categories"), staleTime: Infinity });
  const totalBudget = (budgets.data ?? []).reduce((s, b) => s + b.budget, 0);
  const totalSpent = (budgets.data ?? []).reduce((s, b) => s + b.spent, 0);
  const monthly = (goals.data ?? []).reduce((s, g) => s + g.monthly_needed, 0);
  return (
    <>
      <PageHeader title="Budgets & goals" description="Monthly limits per category, and what you're saving towards. Both feed your insights, the coach and Smart Picks affordability." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Budgets this month" description={budgets.data?.length ? `${inr(totalSpent)} spent of ${inr(totalBudget)} budgeted. The tick on each bar shows where an even pace would be today.` : undefined}>
          {!budgets.data ? <LoaderCircle className="size-5 animate-spin" /> : budgets.data.length === 0
            ? <EmptyState title="No budgets yet">Set a monthly limit for the categories you want to keep an eye on.</EmptyState>
            : <ul className="divide-y divide-border">{budgets.data.map((b) => <BudgetRow key={b.id} b={b} />)}</ul>}
          <AddBudget cats={cats.data ?? []} taken={new Set((budgets.data ?? []).map((b) => b.category_id))} />
        </Card>
        <Card title="Goals" description={goals.data?.length ? `Together they need ${inr(monthly)}/month. Smart Picks funds these first, so a recommendation never delays a goal.` : undefined}>
          {!goals.data ? <LoaderCircle className="size-5 animate-spin" /> : goals.data.length === 0
            ? <EmptyState icon={Target} title="No goals yet">Create a goal to plan a big purchase or build an emergency fund.</EmptyState>
            : <ul className="grid gap-3">{goals.data.map((g) => <GoalCard key={g.id} g={g} />)}</ul>}
          <div className="mt-3"><NewGoal /></div>
        </Card>
      </div>
    </>
  );
}
