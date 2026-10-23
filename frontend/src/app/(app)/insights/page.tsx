"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Bot, CircleAlert, Eraser, Lightbulb, LoaderCircle, Send, ShoppingBag, Sparkles, TriangleAlert, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/app-shell";
import { MiniChart } from "@/components/charts/charts";
import { Card, EmptyState } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { del, get, post } from "@/lib/api";
import { appHref, titleCase } from "@/lib/format";
import type { CoachAnswer, Insight } from "@/lib/types";
import { cn } from "@/lib/utils";

type HistoryItem = { id: number; role: "user" | "assistant"; text: string; intent: string | null; data: Partial<CoachAnswer> | null; at: string };
type Turn = { id: string; role: "user" | "assistant"; text: string; answer?: CoachAnswer };

function severity(i: Insight) {
  if (i.severity >= 80) return { icon: CircleAlert, color: "var(--critical)", label: "Needs attention" };
  if (i.severity >= 60) return { icon: TriangleAlert, color: "var(--warning)", label: "Worth a look" };
  if (["price_drop", "wishlist"].includes(i.kind)) return { icon: ShoppingBag, color: "var(--chart-1)", label: "Wishlist" };
  return { icon: Lightbulb, color: "var(--chart-1)", label: "For your information" };
}

function Answer({ a, onAsk }: { a: CoachAnswer; onAsk: (q: string) => void }) {
  return (
    <div className="grid gap-3">
      <p className="text-sm leading-relaxed whitespace-pre-line">{a.text}</p>
      {a.chart && a.chart.data.length > 0 && <div className="rounded-lg bg-card p-2 ring-1 ring-border"><MiniChart chart={a.chart} /></div>}
      {a.table && a.table.length > 0 && (
        <div className="overflow-x-auto rounded-lg bg-card ring-1 ring-border">
          <table className="w-full text-xs">
            <thead><tr className="text-left text-muted-foreground">{Object.keys(a.table[0]).map((k) => <th key={k} className="px-2 py-1.5 font-medium">{titleCase(k)}</th>)}</tr></thead>
            <tbody>{a.table.map((r, i) => <tr key={i} className="border-t border-border">{Object.values(r).map((v, j) => <td key={j} className="px-2 py-1.5 tabular">{String(v)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
      {a.links.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {a.links.map((l) => l.href
            ? <Button key={l.label} size="sm" variant="outline" render={<Link href={appHref(l.href)} />}>{l.label} <ArrowRight /></Button>
            : <Button key={l.label} size="sm" variant="outline" onClick={() => onAsk(l.ask ?? l.label)}>{l.label}</Button>)}
        </div>
      )}
      <div className="text-[11px] text-muted-foreground">Understood as “{titleCase(a.intent)}” · {Math.round(a.confidence * 100)}% sure · answered from your own data</div>
    </div>
  );
}

function Coach() {
  const qc = useQueryClient();
  const suggestions = useQuery({ queryKey: ["coach-suggestions"], queryFn: () => get<string[]>("/coach/suggestions"), staleTime: Infinity });
  const history = useQuery({ queryKey: ["coach-history"], queryFn: () => get<HistoryItem[]>("/coach/history"), staleTime: Infinity, refetchOnWindowFocus: false });
  const [pending, setPending] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  // The conversation lives in the query cache (seeded from the server), so it survives leaving the page.
  const turns = useMemo<Turn[]>(() => (history.data ?? []).map((h) => ({
    id: String(h.id), role: h.role, text: h.text,
    answer: h.role === "assistant" ? { text: h.text, intent: h.intent ?? "", confidence: 1, chart: null, table: null, links: [], ...(h.data ?? {}) } as CoachAnswer : undefined,
  })), [history.data]);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [turns.length, pending]);
  const ask = useMutation({
    mutationFn: (q: string) => post<CoachAnswer>("/coach/ask", { question: q }),
    onMutate: (q) => { setPending(q); setFailure(null); },
    onSuccess: (a, q) => {
      const at = new Date().toISOString();
      qc.setQueryData<HistoryItem[]>(["coach-history"], (old) => [...(old ?? []),
        { id: -Date.now(), role: "user", text: q, intent: null, data: null, at },
        { id: a.id ?? -Date.now() - 1, role: "assistant", text: a.text, intent: a.intent, data: a, at }]);
    },
    onError: (e) => setFailure((e as Error).message),
    onSettled: () => setPending(null),
  });
  const clear = useMutation({ mutationFn: () => del("/coach/history"), onSuccess: () => { qc.setQueryData(["coach-history"], []); setFailure(null); } });
  const send = (q: string) => { if (q.trim() && !ask.isPending) { ask.mutate(q.trim()); setText(""); } };
  return (
    <section className="flex h-[calc(100dvh-11rem-var(--sa-top)-var(--sa-bottom))] min-h-[420px] flex-col rounded-xl border border-border bg-card md:h-[640px] xl:sticky xl:top-6 xl:h-[calc(100dvh-8rem)] xl:self-start" aria-label="Coach">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Bot className="size-5 text-primary" />
        <div className="flex-1">
          <div className="text-sm font-semibold">Ask FinPilot</div>
          <div className="text-xs text-muted-foreground">Answers come from your own transactions, budgets, goals, forecast and tax data, worked out on your FinPilot server — no outside AI service.</div>
        </div>
        {turns.length > 0 && <Button size="sm" variant="ghost" onClick={() => clear.mutate()}><Eraser /> Clear</Button>}
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {turns.length === 0 && !pending && (
          <div className="grid place-items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <Sparkles className="size-6" /> Ask about your spending, bills, goals, tax, or whether you can afford something.
          </div>
        )}
        {turns.map((t) => (
          <div key={t.id} className={cn("flex", t.role === "user" ? "justify-end" : "justify-start")}>
            <div className={cn("max-w-[92%] rounded-2xl px-3.5 py-2.5", t.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted")}>
              {t.answer ? <Answer a={t.answer} onAsk={send} /> : <p className="text-sm whitespace-pre-line">{t.text}</p>}
            </div>
          </div>
        ))}
        {pending && (
          <div className="flex justify-end"><div className="max-w-[92%] rounded-2xl bg-primary px-3.5 py-2.5 text-sm text-primary-foreground">{pending}</div></div>
        )}
        {ask.isPending && <div className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" /> Thinking…</div>}
        {failure && <div className="rounded-2xl bg-[#fbe4e4] px-3.5 py-2.5 text-sm text-[#a32525]">{failure}</div>}
        <div ref={end} />
      </div>
      <div className="grid gap-2 border-t border-border p-3">
        <div className="flex flex-wrap gap-1.5">
          {(suggestions.data ?? []).map((s) => (
            <button key={s} type="button" onClick={() => send(s)} disabled={ask.isPending}
              className="rounded-full border border-border px-2.5 py-1 text-xs hover:bg-muted disabled:opacity-50 pointer-coarse:px-3 pointer-coarse:py-2">{s}</button>
          ))}
        </div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. How much did I spend on cabs in August?" aria-label="Your question" maxLength={500} />
          <Button type="submit" disabled={!text.trim() || ask.isPending} aria-label="Send"><Send /></Button>
        </form>
      </div>
    </section>
  );
}

export default function InsightsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["insights"], queryFn: () => get<Insight[]>("/insights") });
  const dismiss = useMutation({
    mutationFn: (id: number) => post(`/insights/${id}/dismiss`),
    onMutate: (id) => qc.setQueryData<Insight[]>(["insights"], (old) => old?.filter((i) => i.id !== id)),
    onSettled: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
  return (
    <>
      <PageHeader title="Insights & coach" description="What changed in your money, ranked by how much it matters — and a coach that answers questions from your own data." />
      <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
        <Coach />
        <Card title="Insights" description="Refreshed whenever new transactions arrive and every night.">
          {!q.data ? <LoaderCircle className="size-5 animate-spin" /> : q.data.length === 0 ? (
            <EmptyState icon={Lightbulb} title="Nothing to flag">Insights appear as FinPilot learns your patterns.</EmptyState>
          ) : (
            <ul className="grid gap-2">
              {q.data.map((i) => {
                const s = severity(i);
                return (
                  <li key={i.id} className="flex gap-3 rounded-lg border border-border p-3">
                    <s.icon className="mt-0.5 size-4 shrink-0" style={{ color: s.color }} aria-label={s.label} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{i.title}</div>
                      <p className="mt-0.5 text-sm text-muted-foreground">{i.body}</p>
                      {i.link && <Link href={appHref(i.link)} className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">Open <ArrowRight className="size-3" /></Link>}
                    </div>
                    <button type="button" aria-label="Dismiss" className="-m-1 grid size-8 shrink-0 place-items-center self-start rounded-md text-muted-foreground hover:bg-muted pointer-coarse:size-10" onClick={() => dismiss.mutate(i.id)}><X className="size-4" /></button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
