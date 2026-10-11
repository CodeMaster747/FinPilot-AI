"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, Download, FileSpreadsheet, LoaderCircle, Plus, Search, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Amount, CategoryIcon, EmptyState, NativeSelect, OriginIcon, Pill } from "@/components/common";
import { CsvWizard } from "@/components/csv-wizard";
import { TxnDrawer } from "@/components/txn-drawer";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import type { AnomalyGroup, Category, Txn } from "@/lib/types";

type Page = { items: Txn[]; total: number; page: number; page_size: number; totals: { in: number; out: number } };

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}
function range(preset: string): { start?: string; end?: string } {
  const now = new Date();
  const y = now.getFullYear(), m = now.getMonth();
  if (preset === "this_month") return { start: iso(new Date(y, m, 1, 12)) };
  if (preset === "last_month") return { start: iso(new Date(y, m - 1, 1, 12)), end: iso(new Date(y, m, 0, 12)) };
  if (preset === "3_months") return { start: iso(new Date(y, m - 2, 1, 12)) };
  if (preset === "this_year") return { start: iso(new Date(y, 0, 1, 12)) };
  return {};
}

function ManualDialog({ open, onOpenChange, cats }: { open: boolean; onOpenChange: (o: boolean) => void; cats: Category[] }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ date: iso(new Date()), amount: "", direction: "debit", merchant: "", category_id: "", notes: "" });
  const save = useMutation({
    mutationFn: () => post("/transactions", { ...f, amount: Number(f.amount), category_id: f.category_id ? Number(f.category_id) : null, notes: f.notes || null }),
    onSuccess: () => { toast.success("Transaction added"); qc.invalidateQueries({ queryKey: ["transactions"] }); onOpenChange(false); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add a transaction by hand</DialogTitle></DialogHeader>
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="grid grid-cols-2 gap-3">
            <label className="grid gap-1 text-sm">Date<Input type="date" required value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></label>
            <label className="grid gap-1 text-sm">Amount (₹)<Input type="number" min="1" step="0.01" required value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></label>
          </div>
          <label className="grid gap-1 text-sm">Merchant or description<Input required value={f.merchant} onChange={(e) => setF({ ...f, merchant: e.target.value })} placeholder="e.g. Saravana Stores" /></label>
          <div className="grid grid-cols-2 gap-3">
            <label className="grid gap-1 text-sm">Type
              <NativeSelect value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}>
                <option value="debit">Money out</option><option value="credit">Money in</option>
              </NativeSelect>
            </label>
            <label className="grid gap-1 text-sm">Category
              <NativeSelect value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })}>
                <option value="">Detect automatically</option>
                {cats.filter((c) => c.kind !== "transfer").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </NativeSelect>
            </label>
          </div>
          <label className="grid gap-1 text-sm">Note (optional)<Input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
          <DialogFooter><Button type="submit" disabled={save.isPending}>{save.isPending && <LoaderCircle className="animate-spin" />} Add</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Transactions() {
  const params = useSearchParams();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [direction, setDirection] = useState("");
  const [origin, setOrigin] = useState("");
  const [preset, setPreset] = useState("all");
  const [review, setReview] = useState(false);
  const [hideTransfers, setHideTransfers] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [openId, setOpenId] = useState<number | null>(params.get("id") ? Number(params.get("id")) : null);
  const [manual, setManual] = useState(false);
  const [csv, setCsv] = useState(false);
  const showAnomalies = params.get("anomalies") === "1";

  const cats = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/categories"), staleTime: Infinity });
  const filters = { q, category_id: category, direction, origin, review: review ? true : undefined, include_transfers: !hideTransfers, page, page_size: 50, ...range(preset) };
  const list = useQuery({ queryKey: ["transactions", filters], queryFn: () => get<Page>("/transactions", filters), placeholderData: keepPreviousData });
  const anomalies = useQuery({ queryKey: ["anomalies"], queryFn: () => get<AnomalyGroup[]>("/anomalies"), enabled: showAnomalies });
  const bulk = useMutation({
    mutationFn: (category_id: number) => post("/transactions/bulk", { ids: [...selected], category_id }),
    onSuccess: () => { toast.success(`Updated ${selected.size} transactions`); setSelected(new Set()); qc.invalidateQueries({ queryKey: ["transactions"] }); },
  });
  const anomalyAction = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => post(`/anomalies/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["anomalies"] }),
  });

  const d = list.data;
  const pages = d ? Math.max(1, Math.ceil(d.total / d.page_size)) : 1;
  const reset = () => setPage(1);
  const toggle = (id: number) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <>
      <PageHeader title="Transactions" description="Every payment FinPilot knows about — from bank SMS, emails, receipts, statements or added by hand. Click one to see the evidence behind it."
        actions={<>
          <Button variant="outline" onClick={() => setManual(true)}><Plus /> Add manually</Button>
          <Button variant="outline" onClick={() => setCsv(true)}><FileSpreadsheet /> Import statement</Button>
          <Button variant="outline" render={<a href={`/api/v1/transactions/export.csv?${new URLSearchParams(Object.entries({ q, category_id: category, ...range(preset) }).filter(([, v]) => v) as [string, string][])}`} />}><Download /> Export CSV</Button>
        </>} />

      {showAnomalies && (anomalies.data?.length ?? 0) > 0 && (
        <section className="mb-4 rounded-xl border border-border bg-card p-4">
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><TriangleAlert className="size-4" style={{ color: "var(--serious)" }} /> Unusual transactions</h2>
          <ul className="divide-y divide-border">
            {anomalies.data!.map((a) => (
              <li key={a.transaction.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setOpenId(a.transaction.id)}>
                  <span className="font-medium">{a.transaction.merchant}</span> · {fmtDate(a.transaction.date)} · <Amount value={a.transaction.amount} direction={a.transaction.direction} />
                  <span className="block text-xs text-muted-foreground">{a.explanations[0]}</span>
                </button>
                <Button size="sm" variant="outline" onClick={() => anomalyAction.mutate({ id: a.transaction.id, status: "dismissed" })}>Looks fine</Button>
                <Button size="sm" variant="outline" onClick={() => anomalyAction.mutate({ id: a.transaction.id, status: "confirmed" })}>I&apos;ll check it</Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Search" className="w-56 pl-8" placeholder="Search merchant or note" value={q} onChange={(e) => { setQ(e.target.value); reset(); }} />
        </div>
        <NativeSelect aria-label="Date range" value={preset} onChange={(e) => { setPreset(e.target.value); reset(); }}>
          <option value="all">All time</option><option value="this_month">This month</option><option value="last_month">Last month</option>
          <option value="3_months">Last 3 months</option><option value="this_year">This year</option>
        </NativeSelect>
        <NativeSelect aria-label="Category" value={category} onChange={(e) => { setCategory(e.target.value); reset(); }}>
          <option value="">All categories</option>
          {cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Direction" value={direction} onChange={(e) => { setDirection(e.target.value); reset(); }}>
          <option value="">In and out</option><option value="debit">Money out</option><option value="credit">Money in</option>
        </NativeSelect>
        <NativeSelect aria-label="Source" value={origin} onChange={(e) => { setOrigin(e.target.value); reset(); }}>
          <option value="">All sources</option><option value="sms">SMS</option><option value="email">Email</option><option value="receipt">Receipts</option>
          <option value="csv">Statements</option><option value="manual">Manual</option>
        </NativeSelect>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground"><Checkbox checked={review} onCheckedChange={(v) => { setReview(Boolean(v)); reset(); }} /> Needs review</label>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground"><Checkbox checked={hideTransfers} onCheckedChange={(v) => { setHideTransfers(Boolean(v)); reset(); }} /> Hide transfers</label>
      </div>

      {d && (
        <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
          <span className="text-muted-foreground">{d.total.toLocaleString("en-IN")} transactions</span>
          <span>In <span className="tabular font-medium text-[var(--good-text)]">{inr(d.totals.in)}</span></span>
          <span>Out <span className="tabular font-medium">{inr(d.totals.out)}</span></span>
          <span className="text-xs text-muted-foreground">(totals exclude transfers between your accounts)</span>
        </div>
      )}

      {selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-secondary px-3 py-2 text-sm">
          <span className="font-medium">{selected.size} selected</span>
          <NativeSelect aria-label="Set category" defaultValue="" onChange={(e) => e.target.value && bulk.mutate(Number(e.target.value))}>
            <option value="" disabled>Set category…</option>
            {cats.data?.filter((c) => c.kind !== "transfer").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </NativeSelect>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
        </div>
      )}

      {d && d.items.length === 0 ? (
        <EmptyState icon={ArrowLeftRight} title="No transactions match">Try another filter, or connect SMS or email on the Connections page.</EmptyState>
      ) : (
        <div className={`overflow-x-auto rounded-xl border border-border bg-card ${list.isFetching ? "opacity-70" : ""}`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="hidden w-8 px-3 py-2 sm:table-cell"><span className="sr-only">Select</span></th>
                <th className="hidden px-3 py-2 font-medium sm:table-cell">Date</th>
                <th className="px-3 py-2 font-medium">Merchant</th>
                <th className="hidden px-3 py-2 font-medium sm:table-cell">Category</th>
                <th className="hidden px-3 py-2 font-medium md:table-cell">Account</th>
                <th className="px-3 py-2 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {(d?.items ?? []).map((t) => (
                <tr key={t.id} className="cursor-pointer border-b border-border last:border-0 hover:bg-muted/60" onClick={() => setOpenId(t.id)}>
                  <td className="hidden px-3 py-2 sm:table-cell" onClick={(e) => e.stopPropagation()}><Checkbox aria-label={`Select ${t.merchant}`} checked={selected.has(t.id)} onCheckedChange={() => toggle(t.id)} /></td>
                  <td className="hidden px-3 py-2 whitespace-nowrap text-muted-foreground tabular sm:table-cell">{fmtDate(t.date, "d MMM yy")}</td>
                  <td className="max-w-72 px-3 py-2">
                    <div className="flex items-center gap-1.5 font-medium">
                      <span className="truncate">{t.merchant}</span>
                      <OriginIcon origin={t.origin} className="shrink-0 text-muted-foreground" />
                      {t.items_count > 0 && <Pill>{t.items_count} item{t.items_count === 1 ? "" : "s"}</Pill>}
                    </div>
                    <div className="hidden truncate text-xs text-muted-foreground sm:block">{t.description}</div>
                    <div className="truncate text-xs text-muted-foreground sm:hidden">{fmtDate(t.date, "d MMM")} · {t.is_transfer ? "Transfer" : t.category?.name ?? "—"}{t.needs_review ? " · needs review" : ""}</div>
                  </td>
                  <td className="hidden px-3 py-2 sm:table-cell">
                    <span className="flex items-center gap-1.5">
                      <CategoryIcon icon={t.is_transfer ? "arrow-left-right" : t.category?.icon} className="text-muted-foreground" />
                      <span className="whitespace-nowrap">{t.is_transfer ? "Transfer" : t.category?.name ?? "—"}</span>
                      {t.needs_review && <Pill tone="warn">Review</Pill>}
                      {t.status === "reversed" && <Pill tone="warn">Reversed</Pill>}
                    </span>
                  </td>
                  <td className="hidden max-w-48 truncate px-3 py-2 text-muted-foreground md:table-cell">{t.account?.name ?? "—"}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap"><Amount value={t.amount} direction={t.direction} className={t.is_transfer ? "text-muted-foreground" : ""} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d && pages > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span className="text-muted-foreground tabular">Page {page} of {pages}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
      <TxnDrawer id={openId} onClose={() => setOpenId(null)} />
      <ManualDialog open={manual} onOpenChange={setManual} cats={cats.data ?? []} />
      <CsvWizard open={csv} onOpenChange={setCsv} />
    </>
  );
}

export default function TransactionsPage() {
  return <Suspense><Transactions /></Suspense>;
}
