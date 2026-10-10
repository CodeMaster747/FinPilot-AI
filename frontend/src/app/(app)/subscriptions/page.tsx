"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgePercent, CalendarClock, Layers, LoaderCircle, Mail, MoonStar, Repeat, TrendingUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { HBarChart } from "@/components/charts/charts";
import { Card, CategoryIcon, EmptyState, Pill, StatTile } from "@/components/common";
import { HighlightedText } from "@/components/message-view";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { get, post } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import type { Category, Message } from "@/lib/types";

type Finding = { type: string; saving: number; title: string; detail: string; message_id?: number };
type Sub = {
  id: number; merchant: string; category: Category | null; cadence: string; amount: number; annual_cost: number; first_seen: string; last_charged: string;
  next_expected: string | null; charges: number; status: string; flags: string[]; findings: Finding[]; user_action: "keep" | "cancel" | null;
};
type Data = { items: Sub[]; suggestions: (Finding & { merchant: string })[]; totals: { monthly: number; annual: number; potential_saving: number } };

const TYPE_ICON: Record<string, typeof Repeat> = { dormant: MoonStar, trial_converted: BadgePercent, overlap: Layers, price_increase: TrendingUp };
const PER: Record<string, string> = { weekly: "week", monthly: "month", quarterly: "quarter", annual: "year", yearly: "year" };
const FLAG_TEXT: Record<string, string> = { dormant: "Not used", trial_converted: "Trial → paid", overlap: "Overlaps", price_increase: "Price up" };

function EvidenceDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const m = useQuery({ queryKey: ["message", id], queryFn: () => get<Message>(`/messages/${id}`), enabled: id !== null });
  return (
    <Dialog open={id !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{m.data?.subject || m.data?.sender || "Evidence"}</DialogTitle>
          <DialogDescription>{m.data ? `${m.data.sender} · ${fmtDate(m.data.received_at, "d MMM yyyy")}` : "Loading…"}</DialogDescription>
        </DialogHeader>
        {m.isLoading ? <LoaderCircle className="size-5 animate-spin" /> : m.data?.body
          ? <div className="max-h-80 overflow-auto rounded-lg bg-muted p-3"><HighlightedText text={m.data.body} fields={m.data.fields} /></div>
          : <p className="text-sm text-muted-foreground">The original email text was deleted under your retention setting; the extracted details are kept.</p>}
      </DialogContent>
    </Dialog>
  );
}

export default function SubscriptionsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["subscriptions"], queryFn: () => get<Data>("/subscriptions") });
  const [evidence, setEvidence] = useState<number | null>(null);
  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "keep" | "cancel" | null }) => post(`/subscriptions/${id}/action`, { action }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["subscriptions"] });
      toast.success(v.action === "cancel" ? "Marked to cancel — remember to cancel it with the provider" : v.action === "keep" ? "Got it — we won't suggest this again" : "Undone");
    },
  });
  const d = q.data;
  if (!d) return <><PageHeader title="Subscriptions" /><LoaderCircle className="size-5 animate-spin" /></>;
  if (d.items.length === 0) {
    return (
      <>
        <PageHeader title="Subscriptions" />
        <EmptyState icon={Repeat} title="No subscriptions found yet">Subscriptions are detected from repeating charges at the same merchant — they appear after two or three billing cycles.</EmptyState>
      </>
    );
  }
  const subId = (merchant: string) => d.items.find((s) => s.merchant === merchant);
  const active = d.items.filter((s) => s.status !== "cancelled");
  return (
    <>
      <PageHeader title="Subscriptions" description="Recurring charges found in your transactions, checked against emails for price changes and free trials." />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={Repeat} label="Active subscriptions" value={String(active.length)} />
        <StatTile label="Per month" value={inr(d.totals.monthly)} sub="annual plans spread over 12 months" />
        <StatTile label="Per year" value={inr(d.totals.annual)} />
        <StatTile label="You could save" value={`${inr(d.totals.potential_saving)}/yr`} tone="good" sub="by acting on the suggestions below" />
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Card title="Suggestions, biggest saving first">
          {d.suggestions.length === 0 ? <p className="text-sm text-muted-foreground">Nothing to suggest — every subscription looks used and fairly priced.</p> : (
            <ul className="grid gap-3">
              {d.suggestions.map((s) => {
                const sub = subId(s.merchant);
                const Icon = TYPE_ICON[s.type] ?? Repeat;
                return (
                  <li key={s.merchant + s.type} className="flex gap-3 rounded-lg border border-border p-3">
                    <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-secondary text-secondary-foreground"><Icon className="size-4" /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                        <div className="font-medium">{s.merchant}: {s.title}</div>
                        {s.type === "price_increase"
                          ? <div className="text-sm font-semibold text-[#7a5200] tabular">costs {inr(s.saving)}/yr more</div>
                          : <div className="text-sm font-semibold text-[var(--good-text)] tabular">save {inr(s.saving)}/yr</div>}
                      </div>
                      <p className="mt-0.5 text-sm text-muted-foreground">{s.detail}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {sub?.user_action === "cancel" ? (
                          <><Pill tone="warn">You plan to cancel</Pill><Button size="sm" variant="ghost" onClick={() => act.mutate({ id: sub.id, action: null })}>Undo</Button></>
                        ) : sub && (
                          <>
                            <Button size="sm" variant="outline" onClick={() => act.mutate({ id: sub.id, action: "cancel" })}>I&apos;ll cancel it</Button>
                            <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: sub.id, action: "keep" })}>Keep it</Button>
                          </>
                        )}
                        {s.message_id && <Button size="sm" variant="ghost" onClick={() => setEvidence(s.message_id!)}><Mail /> See the email</Button>}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <HBarChart title="Where the money goes" subtitle="Yearly cost of each subscription" valueLabel="per year"
          data={active.map((s) => ({ label: s.merchant, value: s.annual_cost }))} />
      </div>
      <Card className="mt-4" title="All subscriptions">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="py-2 pr-3 font-medium">Service</th><th className="py-2 pr-3 font-medium">Plan</th>
              <th className="hidden py-2 pr-3 font-medium md:table-cell">Since</th><th className="py-2 pr-3 font-medium">Next charge</th>
              <th className="py-2 pr-3 font-medium">Notes</th><th className="py-2 text-right font-medium">Per year</th>
            </tr></thead>
            <tbody>
              {d.items.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="py-2 pr-3"><span className="flex items-center gap-2"><CategoryIcon icon={s.category?.icon} className="text-muted-foreground" /><span className="font-medium">{s.merchant}</span></span></td>
                  <td className="py-2 pr-3 whitespace-nowrap tabular">{inr(s.amount)} <span className="text-muted-foreground">/ {PER[s.cadence] ?? s.cadence}</span></td>
                  <td className="hidden py-2 pr-3 text-muted-foreground md:table-cell">{fmtDate(s.first_seen, "MMM yyyy")} · {s.charges} charges</td>
                  <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground">{s.next_expected ? <span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5" />{fmtDate(s.next_expected, "d MMM")}</span> : "—"}</td>
                  <td className="py-2 pr-3"><span className="flex flex-wrap gap-1">
                    {s.status === "dormant" && <Pill tone="warn">Not used</Pill>}
                    {s.flags.filter((f) => f !== "dormant").map((f) => <Pill key={f} tone={f === "price_increase" ? "warn" : "neutral"}>{FLAG_TEXT[f] ?? f}</Pill>)}
                    {s.user_action === "keep" && <Pill tone="good">Keeping</Pill>}
                    {s.user_action === "cancel" && <Pill tone="warn">To cancel</Pill>}
                  </span></td>
                  <td className="py-2 text-right tabular font-medium">{inr(s.annual_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <EvidenceDialog id={evidence} onClose={() => setEvidence(null)} />
    </>
  );
}
