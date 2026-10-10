"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Cpu, Download, FlaskConical, LoaderCircle, Plus, RotateCcw, Save, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Card, NativeSelect, Pill } from "@/components/common";
import { Confirm } from "@/components/confirm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, del, get, patch, post } from "@/lib/api";
import { inr } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { type OcrProgress, ocrImage, parseOcr, prepareImage } from "@/lib/ocr";
import type { Account, Category } from "@/lib/types";

type Rule = { id: number; value: string; match_field: string; op: string; category: Category };
type ParsingSet = { set: string; messages: number; classified: number; kind_accuracy: number; amount_exact: number; amount_cases: number; direction_exact: number; direction_cases: number };
type Quality = {
  capabilities: { python: string; platform: string; sqlite: string; sklearn: { ok: boolean; version?: string }; prophet: { ok: boolean; version?: string; fit_seconds?: number; error?: string };
    pdfplumber: { ok: boolean; version?: string }; ocr: { ok: boolean; engine: string }; status: string };
  report: null | {
    generated_for: string; model_version: string;
    categorizer: { accuracy: number; macro_f1: number; test_examples: number; classes: number };
    message_classifier: { accuracy: number; macro_f1: number; test_examples: number; heldout_bank_styles_accuracy: number };
    coach_intents: { intents: number; heldout_accuracy: number; heldout_paraphrases: number };
    parsing: Record<string, ParsingSet>;
    capture?: { truth_transactions: number; dedup_precision: number; dedup_recall: number; transfer_recall: number; false_transfers: number; category_accuracy: number; receipts_linked_correctly: number; receipts: number };
  };
  picks: null | { k: number; picks: number; popularity_baseline: number; evaluated: number };
  forecast_backtest: { model: string; mae: number; rmse: number; wape: number; folds: number }[];
};
type Sample = { name: string; label: string; kind: string; url: string; total: string; date?: string; merchant?: string };
type BenchRow = { name: string; label: string; total: boolean; date: boolean | null; merchant: boolean | null; seconds: number; read: string };

const pct = (v: number | undefined) => (v === undefined ? "—" : `${(v * 100).toFixed(v === 1 ? 0 : 1)}%`);

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg bg-muted px-3 py-2">
      <div className="text-lg font-semibold tabular">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {note && <div className="mt-0.5 text-[11px] text-muted-foreground">{note}</div>}
    </div>
  );
}

function Ok({ ok }: { ok: boolean | null }) {
  if (ok === null) return <span className="text-muted-foreground">—</span>;
  return ok ? <CircleCheck className="size-4 text-[var(--good)]" aria-label="correct" /> : <CircleX className="size-4 text-[var(--critical)]" aria-label="wrong" />;
}

function OcrBenchmark() {
  const samples = useQuery({ queryKey: ["receipt-samples"], queryFn: () => get<Sample[]>("/receipts/samples") });
  const [rows, setRows] = useState<BenchRow[]>([]);
  const [progress, setProgress] = useState<string | null>(null);
  async function run() {
    const list = (samples.data ?? []).filter((s) => s.kind === "image");
    setRows([]);
    try {
      for (const [i, s] of list.entries()) {
        const t0 = performance.now();
        const blob = await (await fetch(s.url, { credentials: "same-origin" })).blob();
        const img = await prepareImage(blob);
        const ocr = await ocrImage(img.blob, img, (p: OcrProgress) => setProgress(`${i + 1}/${list.length} · ${s.label}: ${p.status} ${Math.round(p.progress * 100)}%`));
        const { fields } = await parseOcr(img.blob, s.name, ocr, true);
        const total = Math.abs(Number(fields.total?.value ?? NaN) - Number(s.total)) < 0.01;
        setRows((r) => [...r, {
          name: s.name, label: s.label, total, seconds: (performance.now() - t0) / 1000,
          date: s.date ? fields.date?.value === s.date : null,
          merchant: s.merchant ? (fields.merchant?.value ?? "").toLowerCase() === s.merchant.toLowerCase() : null,
          read: `${fields.merchant?.value ?? "?"} · ${fields.date?.value ?? "?"} · ₹${fields.total?.value ?? "?"}`,
        }]);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setProgress(null);
    }
  }
  const checks = rows.flatMap((r) => [r.total, r.date, r.merchant]).filter((v) => v !== null) as boolean[];
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={run} disabled={progress !== null || !samples.data}>{progress ? <LoaderCircle className="animate-spin" /> : <FlaskConical />} Run OCR benchmark</Button>
        <span className="text-xs text-muted-foreground">{progress ?? "Reads the sample receipt images with tesseract.js in this browser and checks the merchant, date and total against the known values."}</span>
      </div>
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="py-1.5 pr-3 font-medium">Receipt</th><th className="py-1.5 pr-3 font-medium">Merchant</th><th className="py-1.5 pr-3 font-medium">Date</th>
              <th className="py-1.5 pr-3 font-medium">Total</th><th className="py-1.5 text-right font-medium">Time</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} className="border-b border-border last:border-0">
                  <td className="py-1.5 pr-3">{r.label}<div className="text-xs text-muted-foreground">read: {r.read}</div></td>
                  <td className="py-1.5 pr-3"><Ok ok={r.merchant} /></td><td className="py-1.5 pr-3"><Ok ok={r.date} /></td><td className="py-1.5 pr-3"><Ok ok={r.total} /></td>
                  <td className="py-1.5 text-right tabular">{r.seconds.toFixed(1)} s</td>
                </tr>
              ))}
            </tbody>
          </table>
          {progress === null && <p className="mt-2 text-sm font-medium">{checks.filter(Boolean).length} of {checks.length} fields correct ({Math.round((checks.filter(Boolean).length / checks.length) * 100)}%).</p>}
        </div>
      )}
    </div>
  );
}

function QualitySection() {
  const q = useQuery({ queryKey: ["quality"], queryFn: () => get<Quality>("/system/quality") });
  const d = q.data;
  if (!d) return <LoaderCircle className="size-5 animate-spin" />;
  const c = d.capabilities;
  const r = d.report;
  const naive = d.forecast_backtest.find((b) => b.model === "baseline");
  const prophet = d.forecast_backtest.find((b) => b.model === "prophet_schedule");
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap gap-1.5 text-xs">
        <Pill><Cpu className="size-3" /> Python {c.python} · {c.platform}</Pill>
        <Pill>SQLite {c.sqlite}</Pill>
        <Pill tone={c.sklearn.ok ? "good" : "bad"}>scikit-learn {c.sklearn.version ?? "missing"}</Pill>
        <Pill tone={c.prophet.ok ? "good" : "warn"}>{c.prophet.ok ? `Prophet ${c.prophet.version} (test fit ${c.prophet.fit_seconds}s)` : "Prophet unavailable — baseline forecast in use"}</Pill>
        <Pill tone={c.pdfplumber.ok ? "good" : "bad"}>pdfplumber {c.pdfplumber.version ?? "missing"}</Pill>
        <Pill tone="good">OCR: {c.ocr.engine}</Pill>
      </div>
      {!r ? <p className="text-sm text-muted-foreground">The quality report is generated after the first start — check back in a minute.</p> : (
        <>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Reading messages</h3>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <Metric label="Message type, macro F1 (test split)" value={pct(r.message_classifier.macro_f1)} note={`${r.message_classifier.test_examples} messages`} />
              <Metric label="Unseen bank styles (Axis, Kotak)" value={pct(r.parsing.heldout_styles?.kind_accuracy)} note={`amount ${pct(r.parsing.heldout_styles?.amount_exact)} exact`} />
              <Metric label="Hand-written challenge set" value={pct(r.parsing.challenge?.kind_accuracy)} note={`amount ${pct(r.parsing.challenge?.amount_exact)}, direction ${pct(r.parsing.challenge?.direction_exact)}`} />
              <Metric label="Amount & direction, known formats" value={pct(Math.min(r.parsing.known_formats?.amount_exact ?? 0, r.parsing.known_formats?.direction_exact ?? 0))} note={`${r.parsing.known_formats?.amount_cases} cases`} />
            </div>
          </div>
          {r.capture && (
            <div>
              <h3 className="mb-2 text-sm font-semibold">Demo persona: captured vs ground truth ({r.capture.truth_transactions.toLocaleString("en-IN")} transactions)</h3>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Metric label="De-duplication precision / recall" value={`${pct(r.capture.dedup_precision)} / ${pct(r.capture.dedup_recall)}`} note="SMS + email of one payment = one transaction" />
                <Metric label="Own-account transfers found" value={pct(r.capture.transfer_recall)} note={`${r.capture.false_transfers} false transfers`} />
                <Metric label="Category accuracy" value={pct(r.capture.category_accuracy)} />
                <Metric label="Receipts linked to the right payment" value={pct(r.capture.receipts_linked_correctly)} note={`${r.capture.receipts} email receipts`} />
              </div>
            </div>
          )}
          <div>
            <h3 className="mb-2 text-sm font-semibold">Models</h3>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <Metric label="Category model accuracy (freshly generated noisy names)" value={pct(r.categorizer.accuracy)} note={`macro F1 ${pct(r.categorizer.macro_f1)} · ${r.categorizer.classes} classes`} />
              <Metric label="Coach: held-out paraphrases" value={pct(r.coach_intents.heldout_accuracy)} note={`${r.coach_intents.intents} intents, honest fallback below 35% confidence`} />
              {naive && prophet && <Metric label="Forecast error (MAE/day): Prophet vs naive" value={`${inr(prophet.mae)} vs ${inr(naive.mae)}`} note={`${prophet.folds} rolling 30-day backtests`} />}
              {d.picks && <Metric label={`Smart Picks precision@${d.picks.k}`} value={pct(d.picks.picks)} note={`popularity baseline ${pct(d.picks.popularity_baseline)}`} />}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">Model version {r.model_version} · measured {r.generated_for}. Message and capture figures use synthetic data with known answers, plus a hand-written set of formats the models never trained on.</p>
        </>
      )}
      <div>
        <h3 className="mb-2 text-sm font-semibold">Receipt OCR (in this browser)</h3>
        <OcrBenchmark />
      </div>
    </div>
  );
}

// Keyed by the saved preferences, so the form re-initialises after every save.
function Preferences({ prefs }: { prefs: Record<string, unknown> }) {
  const qc = useQueryClient();
  const [f, setF] = useState(() => ({ buffer_floor: String(prefs.buffer_floor ?? 15000), emergency_months: String(prefs.emergency_months ?? 3),
    picks_weekly_cap: String(prefs.picks_weekly_cap ?? 12), retention_days: String(prefs.retention_days ?? 90) }));
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch("/auth/me", { preferences: body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["me"] }); for (const k of [["picks"], ["dashboard"], ["forecast"]]) qc.invalidateQueries({ queryKey: k }); toast.success("Saved"); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <div className="grid gap-4">
      <label className="flex items-start gap-3 text-sm">
        <Switch className="mt-0.5" checked={Boolean(prefs.picks_enabled)} onCheckedChange={(v) => save.mutate({ picks_enabled: Boolean(v) })} />
        <span><span className="font-medium">Smart Picks</span><span className="block text-muted-foreground">Scan the demo stores for products that fit your budget. Off means no recommendations are made.</span></span>
      </label>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(Object.fromEntries(Object.entries(f).map(([k, v]) => [k, Number(v)]))); }}>
        <label className="grid gap-1 text-sm">Safety buffer floor (₹)<Input type="number" min="0" value={f.buffer_floor} onChange={(e) => setF({ ...f, buffer_floor: e.target.value })} />
          <span className="text-xs text-muted-foreground">Never counted as spendable. The buffer is this or one month of must-pays, whichever is higher.</span></label>
        <label className="grid gap-1 text-sm">Emergency fund target (months)<Input type="number" min="1" max="12" value={f.emergency_months} onChange={(e) => setF({ ...f, emergency_months: e.target.value })} />
          <span className="text-xs text-muted-foreground">Until it&apos;s reached, only essentials are suggested as “buy now”.</span></label>
        <label className="grid gap-1 text-sm">Smart Picks per week (max)<Input type="number" min="1" max="30" value={f.picks_weekly_cap} onChange={(e) => setF({ ...f, picks_weekly_cap: e.target.value })} /></label>
        <label className="grid gap-1 text-sm">Keep original message text for (days)<Input type="number" min="7" max="365" value={f.retention_days} onChange={(e) => setF({ ...f, retention_days: e.target.value })} />
          <span className="text-xs text-muted-foreground">After this, the encrypted SMS/email text is deleted; extracted details stay.</span></label>
        <div className="sm:col-span-2"><Button type="submit" variant="outline" disabled={save.isPending}><Save /> Save preferences</Button></div>
      </form>
    </div>
  );
}

function Rules() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => get<Rule[]>("/rules") });
  const cats = useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/categories"), staleTime: Infinity });
  const [value, setValue] = useState("");
  const [category, setCategory] = useState("");
  const add = useMutation({
    mutationFn: () => post("/rules", { value, category_id: Number(category) }),
    onSuccess: () => { setValue(""); setCategory(""); qc.invalidateQueries({ queryKey: ["rules"] }); toast.success("Rule added — it applies to new transactions"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({ mutationFn: (id: number) => del(`/rules/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }) });
  return (
    <div className="grid gap-3">
      {rules.data?.length === 0 && <p className="text-sm text-muted-foreground">No rules yet. Rules are created when you recategorise with “apply to all”.</p>}
      <ul className="divide-y divide-border text-sm">
        {(rules.data ?? []).map((r) => (
          <li key={r.id} className="flex items-center gap-2 py-1.5">
            <span className="flex-1">{r.match_field} {r.op} “<span className="font-medium">{r.value}</span>” → {r.category.name}</span>
            <button type="button" aria-label={`Delete rule ${r.value}`} onClick={() => remove.mutate(r.id)}><Trash2 className="size-3.5 text-muted-foreground" /></button>
          </li>
        ))}
      </ul>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Input className="min-w-40 flex-1" required minLength={2} value={value} onChange={(e) => setValue(e.target.value)} placeholder="Merchant contains… e.g. ramesh kumar" aria-label="Merchant text" />
        <NativeSelect required value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="" disabled>Category…</option>
          {(cats.data ?? []).filter((c) => c.kind !== "transfer").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </NativeSelect>
        <Button type="submit" variant="outline" disabled={add.isPending}><Plus /> Add rule</Button>
      </form>
    </div>
  );
}

function DataControls({ isDemo }: { isDemo: boolean }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [typed, setTyped] = useState("");
  // Resetting recreates the demo user, which ends this session; the sign-in page shows the progress.
  const reset = useMutation({
    mutationFn: () => post<{ job_id: number }>("/settings/reset-demo"),
    onSuccess: () => { qc.clear(); router.replace("/login/"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({
    mutationFn: () => api("/settings/account", { method: "DELETE", body: { confirm: typed } }),
    onSuccess: () => { qc.clear(); router.replace("/login/"); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" render={<a href="/api/v1/settings/export" />}><Download /> Export all my data (JSON)</Button>
        {isDemo
          ? <Button variant="outline" onClick={() => setConfirmReset(true)}><RotateCcw /> Reset the demo</Button>
          : <Button variant="destructive" onClick={() => setConfirmDelete(true)}><Trash2 /> Delete my account</Button>}
      </div>
      <Confirm open={confirmReset} onOpenChange={setConfirmReset} title="Reset the demo?" confirmLabel="Reset" busy={reset.isPending} onConfirm={() => reset.mutate()}>
        Regenerates the demo persona&apos;s 24 months of messages, receipts and settings, undoing anything changed in the demo. You&apos;ll be signed out while it runs (about a minute) — then choose “Try the demo” again.
      </Confirm>
      <Confirm open={confirmDelete} onOpenChange={setConfirmDelete} title="Delete your account?" confirmLabel="Delete everything" destructive
        busy={remove.isPending} onConfirm={() => remove.mutate()}>
        <span className="grid gap-2">
          <span>This permanently deletes your account, every transaction, message, receipt, budget, goal and consent record on this computer.</span>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type DELETE to confirm" aria-label="Type DELETE to confirm" />
        </span>
      </Confirm>
    </div>
  );
}

function ProfileForm({ user }: { user: { name: string; email: string; is_demo: boolean } }) {
  const qc = useQueryClient();
  const [name, setName] = useState(user.name);
  const save = useMutation({ mutationFn: () => patch("/auth/me", { name }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["me"] }); toast.success("Saved"); } });
  return (
    <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <label className="grid gap-1 text-sm">Name<Input value={name} onChange={(e) => setName(e.target.value)} required /></label>
      <div className="text-sm text-muted-foreground">Signed in as {user.email}{user.is_demo && <Pill className="ml-2" tone="blue">Demo account</Pill>}</div>
      <div><Button type="submit" variant="outline" disabled={save.isPending}><Save /> Save</Button></div>
    </form>
  );
}

export default function SettingsPage() {
  const me = useMe();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => get<(Account & { balance: number; balance_source: string })[]>("/accounts") });
  const u = me.data;
  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Profile">{u && <ProfileForm key={u.id} user={u} />}</Card>
        <Card title="Accounts" description="Found automatically from your messages. Balances come from the latest bank alert or statement.">
          <ul className="divide-y divide-border text-sm">
            {(accounts.data ?? []).map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 py-1.5">
                <span>{a.name}<span className="block text-xs text-muted-foreground">{a.balance_source}</span></span>
                <span className={`tabular font-medium ${a.balance < 0 ? "text-[var(--critical)]" : ""}`}>{inr(a.balance)}</span>
              </li>
            ))}
            {accounts.data?.length === 0 && <li className="py-1.5 text-muted-foreground">No accounts yet — connect SMS or email.</li>}
          </ul>
        </Card>
        <Card title="Preferences">{u && <Preferences key={JSON.stringify(u.preferences)} prefs={u.preferences} />}</Card>
        <Card title="Categorisation rules" description="Rules run before the merchant list and the ML model.">
          <Rules />
        </Card>
        <Card title="Your data" description="Everything stays on this computer, in the data folder next to the app." className="lg:col-span-2">
          {u && <DataControls isDemo={u.is_demo} />}
          {u && !u.is_demo && (
            <p className="mt-3 flex items-start gap-2 text-xs text-muted-foreground"><TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              To stop FinPilot reading a source without deleting your account, revoke it on the Connections page.</p>
          )}
        </Card>
        <Card title="System & model quality" description="Measured on this machine. Nothing here needs configuring." className="lg:col-span-2">
          <QualitySection />
        </Card>
      </div>
    </>
  );
}
