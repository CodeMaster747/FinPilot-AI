"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, get, post } from "@/lib/api";

type Preview = { token: string; columns: string[]; rows: string[][]; total: number; guess: Record<string, string | null> };
const FIELDS: { key: string; label: string; required?: boolean }[] = [
  { key: "date", label: "Date", required: true },
  { key: "description", label: "Description / narration", required: true },
  { key: "debit", label: "Money out (debit)" },
  { key: "credit", label: "Money in (credit)" },
  { key: "amount", label: "Signed amount (if one column)" },
  { key: "reference", label: "Reference number" },
  { key: "balance", label: "Balance after each row (sets the account's balance)" },
];
const ACCEPT = ".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export function CsvWizard({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [accountId, setAccountId] = useState<string>("");
  const [newAccount, setNewAccount] = useState({ name: "", kind: "savings", mask: "" });
  const [busy, setBusy] = useState(false);
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => get<{ id: number; name: string }[]>("/accounts"), enabled: open });

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

  const commit = useMutation({
    mutationFn: () => post<{ imported: number; duplicates: number; skipped: number; balance_set: boolean }>("/imports/csv/commit", {
      token: preview!.token, mapping,
      account_id: accountId && accountId !== "new" ? Number(accountId) : null,
      new_account: accountId === "new" ? { name: newAccount.name.trim(), kind: newAccount.kind, mask: newAccount.mask.trim() || null } : null,
    }),
    onSuccess: (r) => {
      toast.success(`Imported ${r.imported} transactions · ${r.duplicates} already captured from SMS/email were skipped · ${r.skipped} rows ignored`
        + (r.balance_set ? " · account balance updated from the statement" : ""));
      for (const k of [["transactions"], ["dashboard"], ["accounts"], ["forecast"]]) qc.invalidateQueries({ queryKey: k });
      setPreview(null);
      onOpenChange(false);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setPreview(null); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import a bank statement</DialogTitle>
          <DialogDescription>Rows that already arrived as SMS or email alerts are recognised and skipped, so nothing is counted twice.</DialogDescription>
        </DialogHeader>
        {!preview ? (
          <div className="grid gap-4">
            <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center hover:bg-muted">
              {busy ? <LoaderCircle className="size-6 animate-spin" /> : <FileUp className="size-6 text-muted-foreground" />}
              <span className="text-sm font-medium">Choose a statement file</span>
              <span className="text-xs text-muted-foreground">CSV or Excel (.xlsx / .xls), as downloaded from your bank&apos;s net banking. PDF statements aren&apos;t supported — download the Excel or CSV version instead.</span>
              <input type="file" accept={ACCEPT} className="sr-only" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
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
                <span>Which account is this statement for?</span>
                <NativeSelect value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  <option value="">Not specified</option>
                  {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  <option value="new">+ A new account…</option>
                </NativeSelect>
              </label>
            </div>
            {accountId === "new" && (
              <div className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-3">
                <label className="grid gap-1 text-sm">Account name<Input required value={newAccount.name} onChange={(e) => setNewAccount({ ...newAccount, name: e.target.value })} placeholder="e.g. Canara savings" /></label>
                <label className="grid gap-1 text-sm">Type
                  <NativeSelect value={newAccount.kind} onChange={(e) => setNewAccount({ ...newAccount, kind: e.target.value })}>
                    <option value="savings">Bank account</option><option value="credit_card">Credit card</option>
                  </NativeSelect>
                </label>
                <label className="grid gap-1 text-sm">Last 4 digits<Input inputMode="numeric" maxLength={4} value={newAccount.mask} onChange={(e) => setNewAccount({ ...newAccount, mask: e.target.value })} /></label>
              </div>
            )}
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
          {preview && <Button onClick={() => commit.mutate()} disabled={commit.isPending || (accountId === "new" && !newAccount.name.trim())}>{commit.isPending && <LoaderCircle className="animate-spin" />} Import {preview.total} rows</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
