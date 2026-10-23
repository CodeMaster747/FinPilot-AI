"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Download, Landmark, LoaderCircle, Pencil, Plus, RotateCcw, Save, Smartphone, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { Card, NativeSelect, Pill } from "@/components/common";
import { Confirm } from "@/components/confirm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, del, endSession, get, patch, post, put } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { inr } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { isNative, serverUrl } from "@/lib/platform";
import type { AccountRow, Category } from "@/lib/types";

type Rule = { id: number; value: string; match_field: string; op: string; category: Category };
type ParsingSet = { set: string; messages: number; classified: number; kind_accuracy: number; amount_exact: number; amount_cases: number;
  direction_exact: number; direction_cases: number; mask_exact?: number | null; payee_found?: number | null; silently_dropped?: number; otps_stored?: number };
type Quality = {
  capabilities: { python: string; platform: string; sqlite: string; sklearn: { ok: boolean; version?: string }; prophet: { ok: boolean; version?: string; fit_seconds?: number; error?: string };
    pdfplumber: { ok: boolean; version?: string }; ocr: { ok: boolean; engine: string }; status: string };
  report: null | {
    generated_for?: string; model_version?: string;
    categorizer?: { accuracy: number; macro_f1: number; test_examples: number; classes: number };
    message_classifier?: { accuracy: number; macro_f1: number; test_examples: number; heldout_bank_styles_accuracy: number };
    coach_intents?: { intents: number; heldout_accuracy: number; heldout_paraphrases: number };
    parsing?: Record<string, ParsingSet>;
    capture?: { truth_transactions: number; dedup_precision: number; dedup_recall: number; transfer_recall: number; false_transfers: number; category_accuracy: number; receipts_linked_correctly: number; receipts: number };
  };
  forecast_backtest: { model: string; mae: number; rmse: number; wape: number; folds: number }[];
};
type Pairing = { lan_urls: string[]; tunnel_url: string | null; tunnel_error: string | null; best_url: string | null; qr_svg: string | null; lan_enabled: boolean };

const pct = (v: number | undefined | null) => (v === undefined || v === null ? "—" : `${(v * 100).toFixed(v === 1 ? 0 : 1)}%`);
const REFRESH = [["accounts"], ["dashboard"], ["forecast"], ["wishlist"], ["me"], ["insights"]];

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg bg-muted px-3 py-2">
      <div className="text-lg font-semibold tabular">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {note && <div className="mt-0.5 text-[11px] text-muted-foreground">{note}</div>}
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
  const real = r?.parsing?.real_formats;
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
      {!r?.parsing ? <p className="text-sm text-muted-foreground">The evaluation is generated after the models are trained (on first start) — check back in a minute.</p> : (
        <>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Reading bank messages</h3>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              {real && <Metric label={`Real bank formats (${real.messages} messages, 25+ institutions)`} value={pct(real.kind_accuracy)}
                note={`amount ${pct(real.amount_exact)} · account ${pct(real.mask_exact)} · payee ${pct(real.payee_found)} · ${real.silently_dropped ?? 0} money messages dropped`} />}
              <Metric label="Hand-written challenge set" value={pct(r.parsing.challenge?.kind_accuracy)} note={`amount ${pct(r.parsing.challenge?.amount_exact)}, direction ${pct(r.parsing.challenge?.direction_exact)}`} />
              <Metric label="Unseen synthetic bank styles" value={pct(r.parsing.heldout_styles?.kind_accuracy)} note={`amount ${pct(r.parsing.heldout_styles?.amount_exact)} exact`} />
              {r.message_classifier && <Metric label="Message type, macro F1 (synthetic test split)" value={pct(r.message_classifier.macro_f1)} note={`${r.message_classifier.test_examples} messages`} />}
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
              {r.categorizer && <Metric label="Category model (freshly generated noisy names)" value={pct(r.categorizer.accuracy)} note={`macro F1 ${pct(r.categorizer.macro_f1)} · ${r.categorizer.classes} classes`} />}
              {r.coach_intents && <Metric label="Coach: held-out paraphrases" value={pct(r.coach_intents.heldout_accuracy)} note={`${r.coach_intents.intents} intents, honest fallback below 35% confidence`} />}
              {naive && prophet && <Metric label="Your forecast error (MAE/day): Prophet vs naive" value={`${inr(prophet.mae)} vs ${inr(naive.mae)}`} note={`${prophet.folds} rolling 30-day backtests on your data`} />}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Model version {r.model_version} · measured {r.generated_for}. The models are trained on synthetic messages. They are measured on held-out synthetic data and on hand-written messages in the formats real banks send; your own data is never used for training.
          </p>
        </>
      )}
    </div>
  );
}

function AccountsCard() {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => get<AccountRow[]>("/accounts") });
  const [editing, setEditing] = useState<number | null>(null);
  const [balance, setBalance] = useState("");
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ name: "", kind: "savings", mask: "", balance: "" });
  const refresh = () => { for (const k of REFRESH) qc.invalidateQueries({ queryKey: k }); };
  const setBal = useMutation({
    mutationFn: ({ id, value }: { id: number; value: number }) => patch(`/accounts/${id}`, { balance: value }),
    onSuccess: () => { setEditing(null); refresh(); toast.success("Balance saved — new transactions move it from here"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const add = useMutation({
    mutationFn: () => post("/accounts", { name: f.name.trim(), kind: f.kind, mask: f.mask.trim() || null, balance: f.balance ? Number(f.balance) : null }),
    onSuccess: () => { setAdding(false); setF({ name: "", kind: "savings", mask: "", balance: "" }); refresh(); toast.success("Account added"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({ mutationFn: (id: number) => del(`/accounts/${id}`), onSuccess: refresh, onError: (e) => toast.error((e as Error).message) });
  return (
    <div id="accounts" className="grid gap-3">
      <ul className="divide-y divide-border text-sm">
        {(accounts.data ?? []).map((a) => (
          <li key={a.id} className="grid gap-2 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0">
                <span className="block truncate">{a.name}</span>
                <span className="block text-xs text-muted-foreground">{a.balance_known ? `balance from ${a.balance_source}` : "balance not known yet"}</span>
              </span>
              <span className={`shrink-0 tabular font-medium ${a.balance !== null && a.balance < 0 ? "text-[var(--critical)]" : ""}`}>
                {a.balance !== null ? inr(a.balance) : "—"}
              </span>
              <Button size="icon-sm" variant="ghost" className="size-10" aria-label={`Set the balance of ${a.name}`}
                onClick={() => { setEditing(a.id); setBalance(a.balance !== null ? String(Math.abs(a.balance)) : ""); }}><Pencil /></Button>
            </div>
            {editing === a.id && (
              <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); setBal.mutate({ id: a.id, value: Number(balance) }); }}>
                <Input type="number" inputMode="decimal" step="0.01" required value={balance} onChange={(e) => setBalance(e.target.value)} className="min-w-32 flex-1"
                  aria-label={a.kind === "credit_card" ? "Amount you owe today" : "Balance today"} placeholder={a.kind === "credit_card" ? "Amount you owe today (₹)" : "Balance today (₹)"} />
                <Button type="submit" disabled={setBal.isPending}>Save</Button>
                <Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                {!a.mask && <Button type="button" variant="ghost" onClick={() => remove.mutate(a.id)}><Trash2 /> Delete</Button>}
              </form>
            )}
          </li>
        ))}
        {accounts.data?.length === 0 && <li className="py-2 text-muted-foreground">No accounts yet. They appear by themselves from your bank SMS and emails, or add one here.</li>}
      </ul>
      {adding ? (
        <form className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <label className="grid gap-1 text-sm">Name<Input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Cash, Paytm wallet, SBI savings" /></label>
          <label className="grid gap-1 text-sm">Type
            <NativeSelect value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option value="savings">Bank account</option><option value="credit_card">Credit card</option><option value="cash">Cash</option><option value="wallet">Wallet</option>
            </NativeSelect>
          </label>
          <label className="grid gap-1 text-sm">Last 4 digits (optional)<Input inputMode="numeric" maxLength={4} value={f.mask} onChange={(e) => setF({ ...f, mask: e.target.value })} placeholder="so bank SMS land here" /></label>
          <label className="grid gap-1 text-sm">{f.kind === "credit_card" ? "Amount owed today (₹)" : "Balance today (₹)"}<Input type="number" inputMode="decimal" step="0.01" value={f.balance} onChange={(e) => setF({ ...f, balance: e.target.value })} /></label>
          <div className="flex gap-2 sm:col-span-2"><Button type="submit" disabled={add.isPending}><Plus /> Add account</Button><Button type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button></div>
        </form>
      ) : (
        <div><Button variant="outline" onClick={() => setAdding(true)}><Landmark /> Add an account</Button></div>
      )}
    </div>
  );
}

// Keyed by the saved preferences, so the forms re-initialise after every save.
function AboutYou({ prefs, city }: { prefs: Record<string, unknown>; city: string }) {
  const qc = useQueryClient();
  const str = (v: unknown) => (v === null || v === undefined ? "" : String(v));
  const [f, setF] = useState(() => ({ take_home: str(prefs.take_home_monthly), payday: str(prefs.payday), rent: str(prefs.rent_monthly),
    rent_day: str(prefs.rent_day), landlord: str(prefs.rent_payee), wants: str(prefs.wants_budget), city }));
  const save = useMutation({
    mutationFn: async () => {
      const n = (v: string) => (v.trim() ? Number(v) : null);
      await patch("/auth/me", { preferences: { take_home_monthly: n(f.take_home), payday: n(f.payday), rent_monthly: n(f.rent), rent_day: n(f.rent_day),
        rent_payee: f.landlord.trim().length >= 2 ? f.landlord.trim() : null, wants_budget: n(f.wants) } });
      if (f.city.trim() !== city) await put("/tax/profile", { city: f.city.trim() || null });
    },
    onSuccess: () => { for (const k of REFRESH) qc.invalidateQueries({ queryKey: k }); toast.success("Saved"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <label className="grid gap-1 text-sm">Take-home pay per month (₹)<Input inputMode="numeric" value={f.take_home} onChange={set("take_home")} />
        <span className="text-xs text-muted-foreground">Used until 2 full months of salary credits have been seen.</span></label>
      <label className="grid gap-1 text-sm">Payday (day of month)<Input inputMode="numeric" value={f.payday} onChange={set("payday")} /></label>
      <label className="grid gap-1 text-sm">Rent per month (₹)<Input inputMode="numeric" value={f.rent} onChange={set("rent")} /></label>
      <label className="grid gap-1 text-sm">Rent day<Input inputMode="numeric" value={f.rent_day} onChange={set("rent_day")} /></label>
      <label className="grid gap-1 text-sm sm:col-span-2">Landlord&apos;s name or UPI ID<Input value={f.landlord} onChange={set("landlord")} />
        <span className="text-xs text-muted-foreground">Payments to them are categorised as Rent, including past ones.</span></label>
      <label className="grid gap-1 text-sm">City (for HRA)<Input value={f.city} onChange={set("city")} /></label>
      <label className="grid gap-1 text-sm">Monthly “wants” budget (₹)<Input inputMode="numeric" value={f.wants} onChange={set("wants")} placeholder="30% of income if empty" /></label>
      <div className="sm:col-span-2"><Button type="submit" variant="outline" disabled={save.isPending}><Save /> Save</Button></div>
    </form>
  );
}

function Preferences({ prefs }: { prefs: Record<string, unknown> }) {
  const qc = useQueryClient();
  const [f, setF] = useState(() => ({ buffer_floor: String(prefs.buffer_floor ?? 10000), emergency_months: String(prefs.emergency_months ?? 3),
    retention_days: String(prefs.retention_days ?? 90) }));
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch("/auth/me", { preferences: body }),
    onSuccess: () => { for (const k of REFRESH) qc.invalidateQueries({ queryKey: k }); toast.success("Saved"); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(Object.fromEntries(Object.entries(f).map(([k, v]) => [k, Number(v)]))); }}>
      <label className="grid gap-1 text-sm">Safety buffer floor (₹)<Input type="number" inputMode="numeric" min="0" value={f.buffer_floor} onChange={(e) => setF({ ...f, buffer_floor: e.target.value })} />
        <span className="text-xs text-muted-foreground">Never counted as spendable. The buffer is this or one month of must-pays, whichever is higher.</span></label>
      <label className="grid gap-1 text-sm">Emergency fund target (months)<Input type="number" inputMode="numeric" min="1" max="12" value={f.emergency_months} onChange={(e) => setF({ ...f, emergency_months: e.target.value })} />
        <span className="text-xs text-muted-foreground">Until it&apos;s reached, nothing beyond everyday needs is marked “buy now”.</span></label>
      <label className="grid gap-1 text-sm">Keep original message text for (days)<Input type="number" inputMode="numeric" min="7" max="365" value={f.retention_days} onChange={(e) => setF({ ...f, retention_days: e.target.value })} />
        <span className="text-xs text-muted-foreground">After this, the encrypted SMS/email text is deleted; extracted details stay.</span></label>
      <div className="sm:col-span-2"><Button type="submit" variant="outline" disabled={save.isPending}><Save /> Save preferences</Button></div>
    </form>
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
          <li key={r.id} className="flex items-center gap-2 py-1">
            <span className="flex-1">{r.match_field} {r.op} “<span className="font-medium">{r.value}</span>” → {r.category.name}</span>
            <button type="button" className="grid size-10 place-items-center rounded-lg hover:bg-muted" aria-label={`Delete rule ${r.value}`} onClick={() => remove.mutate(r.id)}>
              <Trash2 className="size-4 text-muted-foreground" />
            </button>
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

function PhoneCard() {
  const native = isNative();
  const pairing = useQuery({ queryKey: ["pairing"], queryFn: () => get<Pairing>("/system/pairing"), enabled: !native });
  if (native) {
    return (
      <div className="grid gap-2 text-sm">
        <span>This phone is connected to the FinPilot server at <span className="font-medium">{serverUrl()}</span>.</span>
        <div><Button variant="outline" render={<Link href="/connect/" />}><Smartphone /> Change server</Button></div>
      </div>
    );
  }
  const p = pairing.data;
  if (!p) return <LoaderCircle className="size-5 animate-spin" />;
  return (
    <div className="grid gap-4 sm:grid-cols-[180px_1fr]">
      {p.qr_svg ? (
        <div className="rounded-lg bg-white p-2" aria-label={`QR code for ${p.best_url}`} dangerouslySetInnerHTML={{ __html: p.qr_svg }} />
      ) : <div className="grid h-[180px] place-items-center rounded-lg bg-muted p-3 text-center text-xs text-muted-foreground">No network address — connect this computer to Wi-Fi.</div>}
      <div className="grid content-start gap-2 text-sm">
        <span>Install the FinPilot AI Android app, open it and scan this code (or type the address) to connect it to this computer.</span>
        {p.tunnel_url && <span><span className="font-medium">Anywhere:</span> <code className="rounded bg-muted px-1">{p.tunnel_url}</code></span>}
        {p.lan_urls.map((u) => <span key={u}><span className="font-medium">Same Wi-Fi or hotspot:</span> <code className="rounded bg-muted px-1">{u}</code></span>)}
        {!p.lan_enabled && <span className="text-[#a32525]">This server was started with --local-only, so phones can&apos;t reach it.</span>}
        {p.tunnel_error && <span className="text-xs text-muted-foreground">Tunnel: {p.tunnel_error}</span>}
        <span className="text-xs text-muted-foreground">If the phone can&apos;t connect on this network (college Wi-Fi often isolates devices), restart with <code>python3 run.py --tunnel</code>.</span>
      </div>
    </div>
  );
}

function DataControls({ isDemo }: { isDemo: boolean }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [typed, setTyped] = useState("");
  const [exporting, setExporting] = useState(false);
  const reset = useMutation({
    mutationFn: () => post<{ job_id: number }>("/settings/reset-demo"),
    onSuccess: async () => { await endSession(); qc.clear(); router.replace("/login/"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({
    mutationFn: () => api("/settings/account", { method: "DELETE", body: { confirm: typed } }),
    onSuccess: async () => { await endSession(); qc.clear(); router.replace("/login/"); },
    onError: (e) => toast.error((e as Error).message),
  });
  async function exportAll() {
    setExporting(true);
    try {
      await downloadFile("/settings/export", undefined, "finpilot-export.json");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setExporting(false);
    }
  }
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={exportAll} disabled={exporting}>{exporting ? <LoaderCircle className="animate-spin" /> : <Download />} Export all my data (JSON)</Button>
        {isDemo
          ? <Button variant="outline" onClick={() => setConfirmReset(true)}><RotateCcw /> Reset the demo</Button>
          : <Button variant="destructive" onClick={() => setConfirmDelete(true)}><Trash2 /> Delete my account</Button>}
      </div>
      <Confirm open={confirmReset} onOpenChange={setConfirmReset} title="Reset the demo?" confirmLabel="Reset" busy={reset.isPending} onConfirm={() => reset.mutate()}>
        Regenerates the demo persona&apos;s sample data, undoing anything changed in the demo. You&apos;ll be signed out while it runs (about a minute).
      </Confirm>
      <Confirm open={confirmDelete} onOpenChange={setConfirmDelete} title="Delete your account?" confirmLabel="Delete everything" destructive
        busy={remove.isPending} onConfirm={() => remove.mutate()}>
        <span className="grid gap-2">
          <span>This permanently deletes your account and every transaction, message, receipt image, budget, goal, consent record and stored mailbox password on your FinPilot server.</span>
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
      <div className="text-sm text-muted-foreground">Signed in as {user.email}{user.is_demo && <Pill className="ml-2" tone="warn">Demo account — sample data</Pill>}</div>
      <div><Button type="submit" variant="outline" disabled={save.isPending}><Save /> Save</Button></div>
    </form>
  );
}

export default function SettingsPage() {
  const me = useMe();
  const tax = useQuery({ queryKey: ["tax-profile-city"], queryFn: () => get<{ profile: Record<string, unknown> }>("/tax", { year: "2026-27" }) });
  const u = me.data;
  const city = String(tax.data?.profile?.city ?? "");
  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Profile">{u && <ProfileForm key={u.id} user={u} />}</Card>
        <Card title="Accounts" description="Found automatically from your bank messages. Set a balance once, and every transaction after it moves it.">
          <AccountsCard />
        </Card>
        <Card title="About you" description="Helps FinPilot plan before it has months of history.">
          {u && tax.data && <AboutYou key={JSON.stringify(u.preferences) + city} prefs={u.preferences} city={city} />}
        </Card>
        <Card title="Preferences">{u && <Preferences key={JSON.stringify(u.preferences)} prefs={u.preferences} />}</Card>
        <Card title={isNative() ? "Server" : "Connect your phone"} description={isNative() ? undefined : "Read your SMS automatically with the FinPilot Android app."}>
          <PhoneCard />
        </Card>
        <Card title="Categorisation rules" description="Rules run before the merchant list and the ML model.">
          <Rules />
        </Card>
        <Card title="Your data" description="Everything is stored on your FinPilot server (your laptop), in the data folder next to the app." className="lg:col-span-2">
          {u && <DataControls isDemo={u.is_demo} />}
          {u && !u.is_demo && (
            <p className="mt-3 flex items-start gap-2 text-xs text-muted-foreground"><TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              To stop FinPilot reading a source without deleting your account, revoke it on the Connections page.</p>
          )}
        </Card>
        <Card title="Model evaluation" description="How well FinPilot reads messages and forecasts, measured by your FinPilot server." className="lg:col-span-2">
          <QualitySection />
        </Card>
      </div>
    </>
  );
}
