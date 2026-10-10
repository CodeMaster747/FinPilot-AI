"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Link2, LoaderCircle, Mail, MessageSquareText, Plus, ScanLine, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Amount, CategoryIcon, EmptyState, NativeSelect, Pill } from "@/components/common";
import { FieldList, HighlightedText } from "@/components/message-view";
import { TxnDrawer } from "@/components/txn-drawer";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { fmtDate, titleCase } from "@/lib/format";
import type { Category, Message, Txn } from "@/lib/types";

type ReviewMessage = Message & { suggested_transaction?: Txn | null };
type Queue = { messages: ReviewMessage[]; transactions: Txn[]; counts: { messages: number; transactions: number; receipts: number } };

function useInvalidate() {
  const qc = useQueryClient();
  return () => { for (const k of [["review"], ["review-counts"], ["transactions"], ["dashboard"]]) qc.invalidateQueries({ queryKey: k }); };
}

function MessageItem({ m, cats, onOpen }: { m: ReviewMessage; cats: Category[]; onOpen: (id: number) => void }) {
  const invalidate = useInvalidate();
  const f = m.fields ?? {};
  const [form, setForm] = useState({
    amount: f.amount ? String(f.amount.value) : "",
    direction: (f.direction?.value as string) ?? "debit",
    payee: String(f.payee?.value ?? f.merchant?.value ?? ""),
    date: String(f.date?.value ?? m.received_at.slice(0, 10)),
    category_id: "",
  });
  const resolve = useMutation({
    mutationFn: (action: "create" | "link" | "ignore") => post(`/review/messages/${m.id}`, action === "create"
      ? { action, amount: Number(form.amount), direction: form.direction, payee: form.payee || null, date: form.date, category_id: form.category_id ? Number(form.category_id) : null }
      : action === "link" ? { action, transaction_id: m.suggested_transaction?.id } : { action }),
    onSuccess: (_, action) => { toast.success({ create: "Transaction created", link: "Linked to the payment", ignore: "Dismissed" }[action]); invalidate(); },
    onError: (e) => toast.error((e as Error).message),
  });
  const Icon = m.channel === "sms" ? MessageSquareText : Mail;
  return (
    <li className="grid gap-4 rounded-xl border border-border bg-card p-4 lg:grid-cols-[1.3fr_1fr]">
      <div className="grid content-start gap-2">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Icon className="size-4 text-muted-foreground" />
          <span className="font-medium">{m.subject || m.sender}</span>
          <span className="text-muted-foreground">· {fmtDate(m.received_at, "d MMM yyyy, HH:mm")}</span>
          <Pill tone="blue">{titleCase(m.kind)} · {Math.round(m.confidence * 100)}%</Pill>
        </div>
        {m.note && <p className="text-sm text-[#7a5200]">Why it&apos;s here: {m.note}</p>}
        <div className="rounded-lg bg-muted p-3">
          {m.body ? <HighlightedText text={m.body} fields={f} /> : <span className="text-sm text-muted-foreground">Original text deleted under your retention setting.</span>}
        </div>
        <FieldList fields={f} />
      </div>
      <div className="grid content-start gap-3">
        {m.suggested_transaction && (
          <div className="rounded-lg border border-[#c9dcf3] bg-[#f3f7fd] p-3 text-sm">
            <div className="mb-1 text-xs font-medium text-muted-foreground">Possible match</div>
            <button type="button" className="flex w-full items-center justify-between gap-2 text-left" onClick={() => onOpen(m.suggested_transaction!.id)}>
              <span><span className="font-medium">{m.suggested_transaction.merchant}</span> · {fmtDate(m.suggested_transaction.date, "d MMM")}</span>
              <Amount value={m.suggested_transaction.amount} direction={m.suggested_transaction.direction} />
            </button>
            <Button size="sm" className="mt-2" onClick={() => resolve.mutate("link")} disabled={resolve.isPending}><Link2 /> Yes, same payment</Button>
          </div>
        )}
        <form className="grid gap-2" onSubmit={(e) => { e.preventDefault(); resolve.mutate("create"); }}>
          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1 text-xs text-muted-foreground">Amount (₹)<Input type="number" step="0.01" min="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
            <label className="grid gap-1 text-xs text-muted-foreground">Date<Input type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
          </div>
          <label className="grid gap-1 text-xs text-muted-foreground">Paid to / received from<Input value={form.payee} onChange={(e) => setForm({ ...form, payee: e.target.value })} /></label>
          <div className="grid grid-cols-2 gap-2">
            <NativeSelect aria-label="Direction" value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
              <option value="debit">Money out</option><option value="credit">Money in</option>
            </NativeSelect>
            <NativeSelect aria-label="Category" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
              <option value="">Detect category</option>
              {cats.filter((c) => c.kind !== "transfer").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </NativeSelect>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant={m.suggested_transaction ? "outline" : "default"} disabled={resolve.isPending}>
              {resolve.isPending ? <LoaderCircle className="animate-spin" /> : <Plus />} Record as a transaction
            </Button>
            <Button type="button" variant="ghost" onClick={() => resolve.mutate("ignore")} disabled={resolve.isPending}><X /> Not a payment</Button>
          </div>
        </form>
      </div>
    </li>
  );
}

function TxnItem({ t, cats, onOpen }: { t: Txn; cats: Category[]; onOpen: (id: number) => void }) {
  const invalidate = useInvalidate();
  const [cat, setCat] = useState(t.category && t.category.name !== "Misc" ? String(t.category.id) : "");
  const [remember, setRemember] = useState(true);
  const save = useMutation({
    mutationFn: () => post<{ updated: number }>(`/review/transactions/${t.id}`, { category_id: Number(cat), remember }),
    onSuccess: (r) => {
      const others = r.updated - 1;
      toast.success(others > 0 ? `Saved — ${others} other ${t.merchant} payment${others === 1 ? "" : "s"} updated too` : "Saved");
      invalidate();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-3">
      <button type="button" className="flex min-w-48 flex-1 items-center gap-3 text-left" onClick={() => onOpen(t.id)}>
        <CategoryIcon icon={t.category?.icon} className="text-muted-foreground" />
        <span className="min-w-0">
          <span className="block truncate font-medium">{t.merchant}</span>
          <span className="block truncate text-xs text-muted-foreground">{fmtDate(t.date)} · {t.description} · {t.category && t.category.name !== "Misc" && t.category_source === "ml" ? `model's guess: ${t.category.name} (${Math.round(t.category_confidence * 100)}% sure)` : "not enough to go on — no confident category"}</span>
        </span>
      </button>
      <Amount value={t.amount} direction={t.direction} />
      <NativeSelect aria-label={`Category for ${t.merchant}`} value={cat} onChange={(e) => setCat(e.target.value)}>
        <option value="" disabled>Choose category…</option>
        {cats.filter((c) => c.kind !== "transfer").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </NativeSelect>
      <label className="flex items-center gap-1.5 text-xs text-muted-foreground"><Checkbox checked={remember} onCheckedChange={(v) => setRemember(Boolean(v))} /> Remember for {t.merchant}</label>
      <Button size="sm" onClick={() => save.mutate()} disabled={!cat || save.isPending}>{save.isPending ? <LoaderCircle className="animate-spin" /> : <CircleCheck />} Save</Button>
    </li>
  );
}

export default function ReviewPage() {
  const q = useQuery({ queryKey: ["review"], queryFn: () => get<Queue>("/review") });
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/categories"), staleTime: Infinity });
  const [openId, setOpenId] = useState<number | null>(null);
  const d = q.data;
  return (
    <>
      <PageHeader title="Review" description="Everything FinPilot wasn't sure about, in one place. Each answer teaches it — remembered categories apply to future payments automatically." />
      {d && d.counts.receipts > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3 text-sm">
          <ScanLine className="size-4 text-muted-foreground" /> {d.counts.receipts} scanned receipt{d.counts.receipts > 1 ? "s are" : " is"} waiting to be confirmed.
          <Button size="sm" variant="outline" render={<Link href="/scan/" />}>Open Scan</Button>
        </div>
      )}
      {!d ? <LoaderCircle className="size-5 animate-spin" /> : (
        <Tabs defaultValue={d.counts.messages > 0 ? "messages" : "transactions"}>
          <TabsList>
            <TabsTrigger value="messages">Messages <Pill className="ml-1">{d.counts.messages}</Pill></TabsTrigger>
            <TabsTrigger value="transactions">Categories <Pill className="ml-1">{d.counts.transactions}</Pill></TabsTrigger>
          </TabsList>
          <TabsContent value="messages" className="mt-2">
            {d.messages.length === 0
              ? <EmptyState icon={CircleCheck} title="No messages need you">Unclear alerts, unmatched refunds and possible receipt matches show up here.</EmptyState>
              : <ul className="grid gap-3">{d.messages.map((m) => <MessageItem key={m.id} m={m} cats={cats.data ?? []} onOpen={setOpenId} />)}</ul>}
          </TabsContent>
          <TabsContent value="transactions" className="mt-2">
            {d.transactions.length === 0
              ? <EmptyState icon={CircleCheck} title="Every transaction has a category">Payments FinPilot couldn&apos;t categorise confidently show up here.</EmptyState>
              : <ul className="grid gap-2">{d.transactions.map((t) => <TxnItem key={t.id} t={t} cats={cats.data ?? []} onOpen={setOpenId} />)}</ul>}
          </TabsContent>
        </Tabs>
      )}
      <TxnDrawer id={openId} onClose={() => setOpenId(null)} />
    </>
  );
}
