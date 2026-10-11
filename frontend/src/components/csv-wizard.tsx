"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, get, post } from "@/lib/api";

type Preview = { token: string; columns: string[]; rows: string[][]; total: number; guess: Record<string, string | null> };
const FIELDS: { key: string; label: string; required?: boolean }[] = [
  { key: "date", label: "Date", required: true },
  { key: "description", label: "Description / narration", required: true },
  { key: "debit", label: "Money out (debit)" },
  { key: "credit", label: "Money in (credit)" },
  { key: "amount", label: "Signed amount (if one column)" },
  { key: "reference", label: "Reference number" },
];

export function CsvWizard({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [accountId, setAccountId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => get<{ id: number; name: string }[]>("/accounts"), enabled: open });
  const samples = useQuery({ queryKey: ["samples"], queryFn: () => get<{ name: string; label: string; url: string; kind: string }[]>("/samples"), enabled: open });

  async function upload(file: File) {
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const p = await api<Preview>("/imports/csv/preview", { method: "POST", body: fd });
      setPreview(p);
      setMapping(p.guess);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function importSample(url: string, name: string) {
    const res = await fetch(url, { credentials: "same-origin" });
    await upload(new File([await res.blob()], name, { type: "text/csv" }));
  }

  const commit = useMutation({
    mutationFn: () => post<{ imported: number; duplicates: number; skipped: number }>("/imports/csv/commit",
      { token: preview!.token, mapping, account_id: accountId ? Number(accountId) : null }),
    onSuccess: (r) => {
      toast.success(`Imported ${r.imported} transactions · ${r.duplicates} already captured from SMS/email were skipped · ${r.skipped} rows ignored`);
      for (const k of [["transactions"], ["dashboard"]]) qc.invalidateQueries({ queryKey: k });
      setPreview(null);
      onOpenChange(false);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setPreview(null); }}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import a bank statement (CSV)</DialogTitle>
          <DialogDescription>Rows that already arrived as SMS or email alerts are recognised and skipped, so nothing is counted twice.</DialogDescription>
        </DialogHeader>
        {!preview ? (
          <div className="grid gap-4">
            <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center hover:bg-muted">
              {busy ? <LoaderCircle className="size-6 animate-spin" /> : <FileUp className="size-6 text-muted-foreground" />}
              <span className="text-sm font-medium">Choose a CSV file</span>
              <span className="text-xs text-muted-foreground">Most Indian banks let you download statements as CSV from net banking.</span>
              <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
            {samples.data?.filter((s) => s.kind === "csv").map((s) => (
              <Button key={s.name} variant="outline" onClick={() => importSample(s.url, s.name)} disabled={busy}>Use the sample: {s.label}</Button>
            ))}
          </div>
        ) : (
          <div className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              {FIELDS.map((f) => (
                <label key={f.key} className="grid gap-1 text-sm">
                  <span>{f.label}{f.required && " *"}</span>
                  <NativeSelect value={mapping[f.key] ?? ""} onChange={(e) => setMapping({ ...mapping, [f.key]: e.target.value || null })}>
                    <option value="">— not in this file —</option>
                    {preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                  </NativeSelect>
                </label>
              ))}
              <label className="grid gap-1 text-sm">
                <span>Account</span>
                <NativeSelect value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  <option value="">Not specified</option>
                  {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </NativeSelect>
              </label>
            </div>
            <div className="max-h-48 overflow-auto rounded-lg border border-border">
              <table className="w-full text-xs">
                <thead className="bg-muted text-left"><tr>{preview.columns.map((c) => <th key={c} className="px-2 py-1 font-medium">{c}</th>)}</tr></thead>
                <tbody>{preview.rows.map((r, i) => <tr key={i} className="border-t border-border">{r.map((v, j) => <td key={j} className="px-2 py-1 whitespace-nowrap">{v}</td>)}</tr>)}</tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">{preview.total} rows found. Showing the first {preview.rows.length}.</p>
          </div>
        )}
        <DialogFooter>
          {preview && <Button variant="outline" onClick={() => setPreview(null)}>Choose another file</Button>}
          {preview && <Button onClick={() => commit.mutate()} disabled={commit.isPending}>{commit.isPending && <LoaderCircle className="animate-spin" />} Import {preview.total} rows</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
