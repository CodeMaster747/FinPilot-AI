"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, LoaderCircle, Mail, MessageSquareText, Receipt } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Amount, CategoryIcon, NativeSelect, Pill } from "@/components/common";
import { Checkbox } from "@/components/ui/checkbox";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { get, patch } from "@/lib/api";
import { fmtDate, inr, titleCase } from "@/lib/format";
import type { Category, Message, TxnDetail } from "@/lib/types";

const ROLE_TEXT: Record<string, string> = {
  primary: "created this transaction",
  duplicate: "same payment, another channel",
  enrichment: "added line items",
  reversal: "reversed it",
  transfer_pair: "other leg of the transfer",
  suggested: "suggested match",
};

function Evidence({ m }: { m: Message }) {
  const [open, setOpen] = useState(false);
  const full = useQuery({ queryKey: ["message", m.id], queryFn: () => get<Message>(`/messages/${m.id}`), enabled: open });
  const Icon = m.channel === "sms" ? MessageSquareText : Mail;
  return (
    <li className="rounded-lg border border-border p-3">
      <button type="button" className="flex w-full items-start gap-2 text-left" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{m.subject || m.sender}</span>
          <span className="block text-xs text-muted-foreground">{m.channel.toUpperCase()} · {fmtDate(m.received_at, "d MMM, HH:mm")} · {ROLE_TEXT[m.role ?? ""] ?? m.status}</span>
        </span>
        <Pill tone="blue">{titleCase(m.kind)}</Pill>
      </button>
      {open && (
        <div className="mt-2 rounded-md bg-muted p-2 text-xs">
          {full.isLoading && <LoaderCircle className="size-3.5 animate-spin" />}
          {full.data && (full.data.body
            ? <pre className="whitespace-pre-wrap font-sans">{full.data.body}</pre>
            : <span className="text-muted-foreground">Original text deleted under your retention setting — the extracted details are kept.</span>)}
          {full.data?.parser && <div className="mt-1 text-muted-foreground">Read by: {full.data.parser}</div>}
        </div>
      )}
    </li>
  );
}

export function TxnDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["txn", id], queryFn: () => get<TxnDetail>(`/transactions/${id}`), enabled: id !== null });
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/categories"), staleTime: Infinity });
  const [remember, setRemember] = useState(true);
  const update = useMutation({
    mutationFn: (category_id: number) => patch(`/transactions/${id}`, { category_id, remember }),
    onSuccess: () => {
      toast.success(remember ? "Category updated — future payments to this merchant will follow" : "Category updated");
      for (const k of [["txn", id], ["transactions"], ["dashboard"], ["review"], ["review-counts"]]) qc.invalidateQueries({ queryKey: k });
    },
  });
  const t = q.data;
  return (
    <Sheet open={id !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{t ? t.merchant : "Transaction"}</SheetTitle>
          <SheetDescription>{t ? `${fmtDate(t.date, "EEEE, d MMM yyyy")} · ${t.account?.name ?? "No account"}` : "Loading…"}</SheetDescription>
        </SheetHeader>
        {t && (
          <div className="grid gap-5 px-4 pb-6">
            <div className="flex items-baseline justify-between">
              <Amount value={t.amount} direction={t.direction} className="text-3xl font-semibold" />
              <div className="flex gap-1.5">
                {t.is_transfer && <Pill tone="blue"><ArrowLeftRight className="size-3" /> Transfer</Pill>}
                {t.status === "reversed" && <Pill tone="warn">Reversed</Pill>}
                <Pill>{t.origin.toUpperCase()}</Pill>
              </div>
            </div>
            <div className="grid gap-1 text-sm">
              <div className="text-muted-foreground">As it appeared</div>
              <div className="font-medium">{t.description}{t.counterparty ? ` · ${t.counterparty}` : ""}</div>
              {t.ref && <div className="text-xs text-muted-foreground">Reference {t.ref}</div>}
              {t.notes && <div className="text-xs text-muted-foreground">{t.notes}</div>}
            </div>
            {!t.is_transfer && (
              <div className="grid gap-2">
                <div className="flex items-center gap-2 text-sm">
                  <CategoryIcon icon={t.category?.icon} />
                  <span className="font-medium">{t.category?.name ?? "Uncategorised"}</span>
                  <span className="text-xs text-muted-foreground">
                    via {t.category_source === "alias" ? "merchant list" : t.category_source === "ml" ? `ML (${Math.round(t.category_confidence * 100)}% sure)` : t.category_source}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <NativeSelect aria-label="Change category" value={t.category?.id ?? ""} disabled={update.isPending}
                    onChange={(e) => update.mutate(Number(e.target.value))}>
                    {(cats.data ?? []).filter((c) => c.kind !== "transfer").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </NativeSelect>
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Checkbox checked={remember} onCheckedChange={(v) => setRemember(Boolean(v))} /> Apply to all {t.merchant} payments
                  </label>
                </div>
              </div>
            )}
            {t.items.length > 0 && (
              <div>
                <div className="mb-1 flex items-center gap-1.5 text-sm font-medium"><Receipt className="size-4" /> Line items</div>
                <ul className="divide-y divide-border rounded-lg border border-border text-sm">
                  {t.items.map((it, i) => (
                    <li key={i} className="flex justify-between gap-2 px-3 py-1.5">
                      <span className="min-w-0 truncate">{it.description}{it.quantity > 1 ? ` × ${it.quantity}` : ""}</span>
                      <span className="tabular">{inr(it.amount, { decimals: true })}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-1 text-xs text-muted-foreground">From the {t.items[0].source === "receipt" ? "scanned receipt" : "merchant's email receipt"}</div>
              </div>
            )}
            {t.transfer_partner && (
              <div className="text-sm text-muted-foreground">
                Paired with {t.transfer_partner.direction === "credit" ? "a credit of" : "a debit of"} {inr(t.transfer_partner.amount)} on {t.transfer_partner.account?.name}
                — so it isn&apos;t counted as income or spending.
              </div>
            )}
            <div>
              <div className="mb-1 text-sm font-medium">Evidence ({t.evidence.length})</div>
              {t.evidence.length === 0
                ? <p className="text-sm text-muted-foreground">Added {t.origin === "manual" ? "by hand" : `from ${t.origin}`}.</p>
                : <ul className="grid gap-2">{t.evidence.map((m) => <Evidence key={m.id} m={m} />)}</ul>}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
