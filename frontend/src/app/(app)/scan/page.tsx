"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, FileText, ImageUp, Link2, LoaderCircle, Plus, ShieldCheck, Trash2, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Amount, Card, NativeSelect, Pill } from "@/components/common";
import { TxnDrawer } from "@/components/txn-drawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, del, get, post } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import { type OcrProgress, type OcrResult, type ReceiptFields, ocrImage, parseOcr, prepareImage } from "@/lib/ocr";
import type { Category, Txn } from "@/lib/types";
import { cn } from "@/lib/utils";

type Sample = { name: string; label: string; kind: "image" | "pdf"; url: string; total: string };
type ParsedReceipt = { id: number; filename: string; kind: "image" | "pdf"; status: string; fields: ReceiptFields; file_url: string; suggested_match: Txn | null; transaction: Txn | null; ocr_text: string };
type ReceiptRow = { id: number; filename: string; kind: string; status: string; created_at: string; total: string | null; merchant: string | null };
type Item = { description: string; quantity: number; amount: string };

const LOW = 0.8;

function Overlay({ ocr, fields }: { ocr: OcrResult; fields: ReceiptFields }) {
  const key = (b: { y0: number; x0: number } | null | undefined) => (b ? `${b.x0}:${b.y0}` : "");
  const roles = new Map<string, string>();
  for (const k of ["merchant", "date", "total"] as const) if (fields[k]?.bbox) roles.set(key(fields[k]!.bbox), k);
  for (const it of fields.items ?? []) if (it.bbox && !roles.has(key(it.bbox))) roles.set(key(it.bbox), "item");
  const COLORS: Record<string, string> = { merchant: "#eb6834", date: "#c98500", total: "#2a78d6", item: "#1baf7a" };
  return (
    <svg viewBox={`0 0 ${ocr.width} ${ocr.height}`} className="pointer-events-none absolute inset-0 size-full" aria-hidden>
      {ocr.lines.map((l, i) => {
        const role = roles.get(key(l.bbox));
        const low = l.confidence < LOW * 100;
        return (
          <rect key={i} x={l.bbox.x0 - 3} y={l.bbox.y0 - 3} width={l.bbox.x1 - l.bbox.x0 + 6} height={l.bbox.y1 - l.bbox.y0 + 6} rx={4}
            fill={role ? COLORS[role] : "transparent"} fillOpacity={role ? 0.14 : 0}
            stroke={role ? COLORS[role] : low ? "#fab219" : "#898781"} strokeOpacity={role ? 1 : 0.55} strokeWidth={role ? 3 : 1.5}
            strokeDasharray={!role && low ? "6 4" : undefined} vectorEffect="non-scaling-stroke" />
        );
      })}
    </svg>
  );
}

function Conf({ c }: { c?: number }) {
  if (c === undefined) return null;
  const low = c < LOW;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs", low ? "text-[#7a5200]" : "text-muted-foreground")}>
      {low && <TriangleAlert className="size-3" aria-hidden />}{Math.round(c * 100)}% sure{low && " — please check"}
    </span>
  );
}

function ReviewForm({ r, onSaved }: { r: ParsedReceipt; onSaved: (t: Txn) => void }) {
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/categories"), staleTime: Infinity });
  const f = r.fields;
  const [merchant, setMerchant] = useState(f.merchant?.value ?? "");
  const [date, setDate] = useState(f.date?.value ?? new Date().toISOString().slice(0, 10));
  const [total, setTotal] = useState(f.total?.value ?? "");
  const [items, setItems] = useState<Item[]>((f.items ?? []).map((i) => ({ description: i.description, quantity: i.quantity, amount: i.amount })));
  const [category, setCategory] = useState("");
  const [link, setLink] = useState<boolean>(!!r.suggested_match);
  const save = useMutation({
    mutationFn: () => post<{ transaction: Txn; linked: boolean }>(`/receipts/${r.id}/commit`, {
      merchant, date, total: Number(total), items, category_id: category ? Number(category) : null,
      transaction_id: link && r.suggested_match ? r.suggested_match.id : null,
    }),
    onSuccess: (res) => {
      toast.success(res.linked ? `Receipt attached to your ${inr(res.transaction.amount)} payment at ${res.transaction.merchant}` : "Saved as a new transaction");
      for (const k of [["transactions"], ["dashboard"], ["receipts"], ["review-counts"]]) qc.invalidateQueries({ queryKey: k });
      onSaved(res.transaction);
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const itemSum = items.reduce((s, i) => s + Number(i.amount || 0), 0);
  return (
    <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm sm:col-span-2">
          <span className="flex items-center justify-between gap-2">Merchant <Conf c={f.merchant?.confidence} /></span>
          <Input required value={merchant} onChange={(e) => setMerchant(e.target.value)} className={cn((f.merchant?.confidence ?? 0) < LOW && "border-[#fab219]")} />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="flex items-center justify-between gap-2">Date <Conf c={f.date?.confidence} /></span>
          <Input type="date" required value={date} onChange={(e) => setDate(e.target.value)} className={cn(f.date && f.date.confidence < LOW && "border-[#fab219]")} />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="flex items-center justify-between gap-2">Total (₹) <Conf c={f.total?.confidence} /></span>
          <Input type="number" step="0.01" min="0.01" required value={total} onChange={(e) => setTotal(e.target.value)} className={cn((f.total?.confidence ?? 0) < LOW && "border-[#fab219]")} />
        </label>
      </div>
      {(f.gstin || f.cgst || f.sgst) && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          {f.gstin && <Pill>GSTIN {f.gstin.value}</Pill>}
          {f.cgst && <Pill>CGST {inr(Number(f.cgst.value), { decimals: true })}</Pill>}
          {f.sgst && <Pill>SGST {inr(Number(f.sgst.value), { decimals: true })}</Pill>}
        </div>
      )}
      {items.length > 0 && (
        <div>
          <div className="mb-1 flex items-center justify-between text-sm font-medium">
            Line items
            <span className={cn("text-xs font-normal", Math.abs(itemSum - Number(total)) <= Number(total) * 0.02 ? "text-[var(--good-text)]" : "text-muted-foreground")}>
              items add up to {inr(itemSum, { decimals: true })}
            </span>
          </div>
          <ul className="divide-y divide-border rounded-lg border border-border text-sm">
            {items.map((it, i) => (
              <li key={i} className="flex items-center gap-2 px-2 py-1">
                <input aria-label="Item" className="min-w-0 flex-1 bg-transparent outline-none" value={it.description}
                  onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} />
                <span className="text-xs text-muted-foreground">×{it.quantity}</span>
                <input aria-label="Amount" className="w-20 bg-transparent text-right tabular outline-none" value={it.amount}
                  onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))} />
                <button type="button" aria-label="Remove item" onClick={() => setItems(items.filter((_, j) => j !== i))}><Trash2 className="size-3.5 text-muted-foreground" /></button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.suggested_match ? (
        <fieldset className="grid gap-2 rounded-lg border border-border p-3 text-sm">
          <legend className="px-1 font-medium">Is this the same as a payment you already have?</legend>
          <label className="flex items-start gap-2">
            <input type="radio" name="link" checked={link} onChange={() => setLink(true)} className="mt-1" />
            <span>
              <span className="flex items-center gap-1 font-medium"><Link2 className="size-3.5" /> Yes — attach it to {r.suggested_match.merchant}, {fmtDate(r.suggested_match.date, "d MMM")}</span>
              <span className="text-muted-foreground"><Amount value={r.suggested_match.amount} direction="debit" /> from {r.suggested_match.origin.toUpperCase()} · {r.suggested_match.account?.name}. Adds the line items without counting it twice.</span>
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input type="radio" name="link" checked={!link} onChange={() => setLink(false)} className="mt-1" />
            <span><span className="font-medium">No — it&apos;s a separate payment</span> <span className="text-muted-foreground">(for example, paid in cash)</span></span>
          </label>
        </fieldset>
      ) : (
        <p className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">No matching card or UPI payment found — this will be recorded as a new payment (for example, cash).</p>
      )}
      <label className="grid gap-1 text-sm">Category
        <NativeSelect value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Detect automatically</option>
          {(cats.data ?? []).filter((c) => c.kind === "expense").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </NativeSelect>
      </label>
      <div className="flex justify-end">
        <Button type="submit" disabled={save.isPending}>{save.isPending ? <LoaderCircle className="animate-spin" /> : <CircleCheck />} {link && r.suggested_match ? "Attach receipt" : "Save payment"}</Button>
      </div>
    </form>
  );
}

export default function ScanPage() {
  const qc = useQueryClient();
  const samples = useQuery({ queryKey: ["receipt-samples"], queryFn: () => get<Sample[]>("/receipts/samples") });
  const recent = useQuery({ queryKey: ["receipts"], queryFn: () => get<ReceiptRow[]>("/receipts") });
  const [preview, setPreview] = useState<string | null>(null);
  const [ocr, setOcr] = useState<OcrResult | null>(null);
  const [progress, setProgress] = useState<OcrProgress | null>(null);
  const [receipt, setReceipt] = useState<ParsedReceipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Txn | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const busy = progress !== null;
  const fileInput = useRef<HTMLInputElement>(null);

  function reset() {
    setPreview(null); setOcr(null); setReceipt(null); setError(null); setSaved(null); setProgress(null);
  }

  async function handle(file: File) {
    reset();
    try {
      if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
        setProgress({ status: "Reading the PDF's text", progress: 0.5 });
        const fd = new FormData();
        fd.append("file", file);
        setReceipt(await api<ParsedReceipt>("/receipts/parse-pdf", { method: "POST", body: fd }));
      } else {
        const img = await prepareImage(file);
        setPreview(img.url);
        const result = await ocrImage(img.blob, img, setProgress);
        setOcr(result);
        setProgress({ status: "Finding the total, date and items", progress: 1 });
        setReceipt(await parseOcr(img.blob, file.name, result) as unknown as ParsedReceipt);
      }
      qc.invalidateQueries({ queryKey: ["receipts"] });
    } catch (e) {
      setError((e as Error).message || "Couldn't read that file.");
    } finally {
      setProgress(null);
    }
  }

  async function trySample(s: Sample) {
    const res = await fetch(s.url, { credentials: "same-origin" });
    const blob = await res.blob();
    await handle(new File([blob], s.name, { type: blob.type || (s.kind === "pdf" ? "application/pdf" : "image/png") }));
  }

  async function reopen(id: number) {
    reset();
    const r = await get<ParsedReceipt>(`/receipts/${id}`);
    setReceipt(r);
    if (r.kind === "image") setPreview(r.file_url);
  }

  return (
    <>
      <PageHeader title="Scan a receipt" description="Optional — most payments already arrive through SMS and email. Scan a receipt to add line items, or to record a cash payment." />
      <div className="mb-4 flex items-start gap-2 rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-[var(--good)]" />
        Text recognition runs inside your browser (tesseract.js). Only the recognised text and the image you choose to keep are sent to FinPilot.
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="grid content-start gap-4">
          <Card title="Choose a receipt">
            <label className={cn("flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center hover:bg-muted", busy && "pointer-events-none opacity-60")}
              onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handle(f); }}>
              <ImageUp className="size-7 text-muted-foreground" />
              <span className="text-sm font-medium">Drop a photo or PDF here, or click to choose</span>
              <span className="text-xs text-muted-foreground">JPG, PNG or WebP photos · digital PDF bills</span>
              <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" className="sr-only"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handle(f); e.target.value = ""; }} />
            </label>
            {(samples.data?.length ?? 0) > 0 && (
              <div className="mt-3 grid gap-1.5">
                <div className="text-xs font-medium text-muted-foreground">Or try a sample:</div>
                <div className="flex flex-wrap gap-1.5">
                  {samples.data!.map((s) => (
                    <Button key={s.name} size="sm" variant="outline" disabled={busy} onClick={() => trySample(s)}>
                      {s.kind === "pdf" ? <FileText /> : <ImageUp />} {s.label}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </Card>
          {(preview || busy) && (
            <Card title="What was read" description={ocr ? `${ocr.lines.length} lines · ${Math.round(ocr.confidence)}% average confidence · ${(ocr.ms / 1000).toFixed(1)} s` : undefined}>
              {busy && progress && (
                <div className="mb-3 grid gap-1.5 text-sm" role="status">
                  <div className="flex items-center gap-2"><LoaderCircle className="size-4 animate-spin" /> {progress.status}…</div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.max(3, progress.progress * 100)}%` }} /></div>
                </div>
              )}
              {(ocr?.image || preview) && (
                <div className="relative mx-auto w-fit max-w-full overflow-hidden rounded-lg border border-border bg-white">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={ocr?.image || preview!} alt="Receipt" className="block max-h-[640px] w-auto max-w-full" />
                  {ocr && receipt && <Overlay ocr={ocr} fields={receipt.fields} />}
                </div>
              )}
              {ocr && receipt && (
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                  {[["#eb6834", "Merchant"], ["#c98500", "Date"], ["#2a78d6", "Total"], ["#1baf7a", "Line item"]].map(([c, l]) => (
                    <span key={l} className="flex items-center gap-1"><span className="inline-block size-2.5 rounded-sm" style={{ background: c }} />{l}</span>
                  ))}
                  <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-3 rounded-sm border border-dashed border-[#fab219]" />Low confidence</span>
                </div>
              )}
            </Card>
          )}
        </div>
        <div className="grid content-start gap-4">
          {error && <div className="flex items-start gap-2 rounded-xl border border-[#f3c4c4] bg-[#fdf3f3] p-4 text-sm text-[#a32525]"><TriangleAlert className="mt-0.5 size-4 shrink-0" />{error}</div>}
          {saved ? (
            <Card title="Saved">
              <div className="grid gap-3 text-sm">
                <button type="button" className="flex items-center justify-between rounded-lg bg-muted px-3 py-2 text-left hover:bg-secondary" onClick={() => setOpenId(saved.id)}>
                  <span><span className="font-medium">{saved.merchant}</span> · {fmtDate(saved.date)} · {saved.category?.name}</span>
                  <Amount value={saved.amount} direction={saved.direction} />
                </button>
                <Button variant="outline" onClick={() => { reset(); fileInput.current?.click(); }}><Plus /> Scan another</Button>
              </div>
            </Card>
          ) : receipt ? (
            receipt.status === "committed" ? (
              <Card title="Already saved"><p className="text-sm text-muted-foreground">This receipt was saved earlier.</p></Card>
            ) : (
              <Card title="Check and save" description={receipt.kind === "pdf" ? "Read from the PDF's text layer." : "Fields below 80% confidence are highlighted — please check them."}>
                <ReviewForm key={receipt.id} r={receipt} onSaved={(t) => setSaved(t)} />
              </Card>
            )
          ) : !busy && (
            <Card title="How it works">
              <ol className="grid list-decimal gap-1.5 pl-5 text-sm text-muted-foreground">
                <li>Text is recognised in your browser.</li>
                <li>FinPilot finds the merchant, date, total, GST and line items, and shows how sure it is about each.</li>
                <li>If a card or UPI payment matches, the receipt is attached to it — adding the items without counting the payment twice.</li>
                <li>Cash receipts become new payments.</li>
              </ol>
            </Card>
          )}
          {(recent.data?.length ?? 0) > 0 && (
            <Card title="Recent receipts">
              <ul className="divide-y divide-border text-sm">
                {recent.data!.slice(0, 8).map((r) => (
                  <li key={r.id} className="flex items-center gap-2 py-2">
                    <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => reopen(r.id)}>
                      {r.merchant ?? r.filename} <span className="text-muted-foreground">· {fmtDate(r.created_at, "d MMM, HH:mm")}</span>
                    </button>
                    {r.total && <span className="tabular">{inr(Number(r.total), { decimals: true })}</span>}
                    <Pill tone={r.status === "committed" ? "good" : "warn"}>{r.status === "committed" ? "Saved" : "To check"}</Pill>
                    {r.status !== "committed" && (
                      <button type="button" aria-label="Discard" onClick={async () => { await del(`/receipts/${r.id}`); qc.invalidateQueries({ queryKey: ["receipts"] }); qc.invalidateQueries({ queryKey: ["review-counts"] }); }}>
                        <Trash2 className="size-3.5 text-muted-foreground" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
      <TxnDrawer id={openId} onClose={() => setOpenId(null)} />
    </>
  );
}
