"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, CircleCheck, Download, FileText, Info, Lightbulb, LoaderCircle, Scale } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { HBarChart } from "@/components/charts/charts";
import { Card, Pill } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { get, put } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { fmtDate, inr } from "@/lib/format";
import { cn } from "@/lib/utils";

type Regime = { taxable: number; slab_tax: number; rebate: number; surcharge: number; cess: number; total: number; effective_rate: number; deductions: { name: string; amount: number }[] };
type Tax = {
  year: string; label: string; act: string; in_progress: boolean; as_of: string; months_left: number; disclaimer: string;
  income: { gross_salary: number; other_income: number; estimated_salary: boolean };
  regimes: { old: Regime; new: Regime };
  recommendation: { regime: "old" | "new"; saving: number; text: string };
  section_80c: { parts: { name: string; amount: number }[]; total: number; limit: number; allowed: number };
  hra: { received: number; rent_paid: number; exempt: number; rule: string; rent_source: "transactions" | "entered" | null; metro: boolean; city: string | null; city_known: boolean };
  headroom: { section: string; used: number; limit: number; tip: string }[];
  advance_tax: { tds_known: boolean; tds: number; balance_due: number | null; needed: boolean; schedule: { due: string; cumulative_pct: number; amount: number }[] };
  evidence: { label: string; amount: number; projected: number; items: { id: number; date: string; merchant: string; amount: number }[] }[];
  profile: Record<string, string | number | boolean | null>;
  years: { id: string; label: string; act: string }[];
};

const PROFILE_FIELDS: [string, string][] = [
  ["gross_salary", "Gross salary per year (FY 2025-26, from Form 16)"], ["basic_salary", "Basic salary (per year)"], ["hra_received", "HRA received (per year)"],
  ["rent_monthly", "Rent paid per month (if not seen in your payments)"], ["employee_pf", "Your PF contribution (per year)"],
  ["professional_tax", "Professional tax"], ["tds_deducted", "TDS deducted by your employer this year"],
  ["other_80c", "Other 80C: PPF, home-loan principal, children's tuition…"], ["nps_80ccd1b", "Your own NPS contribution (80CCD(1B))"],
  ["health_insurance_parents", "Health insurance you pay for your parents"], ["education_loan_interest", "Education-loan interest (certificate)"],
  ["home_loan_interest", "Home-loan interest"],
];

// Keyed by the saved profile, so it re-initialises from the server after every save.
function ProfileForm({ profile, onSaved }: { profile: Tax["profile"]; onSaved: () => void }) {
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(PROFILE_FIELDS.map(([k]) => [k, profile[k] === null || profile[k] === undefined ? "" : String(profile[k])])));
  const [city, setCity] = useState(String(profile.city ?? ""));
  const [seniorParents, setSeniorParents] = useState(Boolean(profile.parents_senior));
  const save = useMutation({
    mutationFn: () => put("/tax/profile", {
      ...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() === "" ? null : Number(v)])),
      city: city.trim() || null, parents_senior: seniorParents, metro: null,
    }),
    onSuccess: () => { toast.success("Tax details saved"); onSaved(); },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">City you live in (for HRA)
          <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Chennai" />
        </label>
        {PROFILE_FIELDS.map(([k, label]) => (
          <label key={k} className="grid gap-1 text-sm">{label}
            <Input type="number" inputMode="numeric" min="0" step="1" value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          </label>
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm"><Switch checked={seniorParents} onCheckedChange={(v) => setSeniorParents(Boolean(v))} /> My parents are senior citizens (higher health-insurance limit)</label>
      <div className="flex justify-end"><Button type="submit" disabled={save.isPending}>{save.isPending && <LoaderCircle className="animate-spin" />} Save and recalculate</Button></div>
    </form>
  );
}

function ExportButtons({ year }: { year: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  async function run(kind: "csv" | "pdf") {
    setBusy(kind);
    try {
      await downloadFile(`/tax/export.${kind}`, { year }, `finpilot-tax-${year}.${kind}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  return (
    <>
      <Button variant="outline" onClick={() => run("csv")} disabled={busy !== null}>{busy === "csv" ? <LoaderCircle className="animate-spin" /> : <Download />} CSV</Button>
      <Button variant="outline" onClick={() => run("pdf")} disabled={busy !== null}>{busy === "pdf" ? <LoaderCircle className="animate-spin" /> : <FileText />} PDF summary</Button>
    </>
  );
}

function Row({ label, value, strong, muted }: { label: string; value: string; strong?: boolean; muted?: boolean }) {
  return (
    <div className={cn("flex justify-between gap-3 py-1", strong && "font-semibold", muted && "text-muted-foreground")}>
      <span>{label}</span><span className="tabular">{value}</span>
    </div>
  );
}

function RegimeColumn({ name, r, recommended, gross, other }: { name: string; r: Regime; recommended: boolean; gross: number; other: number }) {
  return (
    <div className={cn("rounded-xl border p-4", recommended ? "border-primary ring-1 ring-primary/30" : "border-border")}>
      <div className="mb-2 flex items-center justify-between">
        <div className="font-semibold">{name}</div>
        {recommended && <Pill tone="blue"><CircleCheck className="size-3" /> Better for you</Pill>}
      </div>
      <div className="text-sm">
        <Row label="Salary" value={inr(gross)} />
        {other > 0 && <Row label="Interest income" value={inr(other)} />}
        {r.deductions.map((d) => <Row key={d.name} label={`− ${d.name}`} value={inr(d.amount)} muted />)}
        <div className="my-1 border-t border-border" />
        <Row label="Taxable income" value={inr(r.taxable)} strong />
        <Row label="Tax on slabs" value={inr(r.slab_tax)} muted />
        {r.rebate > 0 && <Row label="− Rebate (87A)" value={inr(r.rebate)} muted />}
        {r.surcharge > 0 && <Row label="Surcharge" value={inr(r.surcharge)} muted />}
        <Row label="Health & education cess (4%)" value={inr(r.cess)} muted />
        <div className="my-1 border-t border-border" />
        <Row label="Total tax" value={inr(r.total)} strong />
        <Row label="Effective rate" value={`${r.effective_rate.toFixed(1)}%`} muted />
      </div>
    </div>
  );
}

export default function TaxPage() {
  const qc = useQueryClient();
  const [year, setYear] = useState("2026-27");
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["tax", year], queryFn: () => get<Tax>("/tax", { year }) });
  const t = q.data;
  return (
    <>
      <PageHeader title="Tax" description="Old vs new regime, deductions found in your transactions, and what's left to claim."
        actions={t && <ExportButtons year={year} />} />
      <div className="mb-4 inline-flex rounded-lg bg-muted p-1" role="tablist" aria-label="Year">
        {(t?.years ?? [{ id: "2025-26", label: "FY 2025-26", act: "" }, { id: "2026-27", label: "Tax Year 2026-27", act: "" }]).map((y) => (
          <button key={y.id} type="button" role="tab" aria-selected={year === y.id} onClick={() => setYear(y.id)}
            className={cn("rounded-md px-3 py-1.5 text-sm font-medium", year === y.id ? "bg-card shadow-sm" : "text-muted-foreground hover:text-foreground")}>
            {y.label}
          </button>
        ))}
      </div>
      {!t ? <LoaderCircle className="size-5 animate-spin" /> : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-4">
            <Scale className="size-5 text-primary" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold">{t.recommendation.text}</div>
              <div className="text-sm text-muted-foreground">
                {t.label} · {t.act}{t.in_progress ? ` · in progress — figures to ${fmtDate(t.as_of)} plus your scheduled payments for the remaining ${t.months_left} months` : " · complete year"}
                {t.income.estimated_salary && " · salary estimated from your take-home pay — add your Form 16 figures below for accuracy"}
              </div>
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-[1fr_1fr_0.9fr]">
            <RegimeColumn name="New regime" r={t.regimes.new} recommended={t.recommendation.regime === "new"} gross={t.income.gross_salary} other={t.income.other_income} />
            <RegimeColumn name="Old regime" r={t.regimes.old} recommended={t.recommendation.regime === "old"} gross={t.income.gross_salary} other={t.income.other_income} />
            <div className="grid content-start gap-4">
              <HBarChart title="Total tax" valueLabel="tax" data={[{ label: "New regime", value: t.regimes.new.total }, { label: "Old regime", value: t.regimes.old.total }]}
                highlight={t.recommendation.regime === "new" ? "New regime" : "Old regime"} />
              <Card title="Advance tax">
                {!t.advance_tax.tds_known ? (
                  <p className="flex gap-2 text-sm text-muted-foreground"><Info className="mt-0.5 size-4 shrink-0" />
                    Enter the TDS your employer deducts (from your payslips or Form 16) under “Your salary details” to see whether you owe advance tax.</p>
                ) : t.advance_tax.needed ? (
                  <ul className="divide-y divide-border text-sm">
                    {t.advance_tax.schedule.map((s) => (
                      <li key={s.due} className="flex justify-between py-1.5"><span>{s.due} · {s.cumulative_pct}% by then</span><span className="tabular font-medium">{inr(s.amount)}</span></li>
                    ))}
                  </ul>
                ) : (
                  <p className="flex gap-2 text-sm text-muted-foreground"><CircleCheck className="mt-0.5 size-4 shrink-0 text-[var(--good)]" />
                    Your TDS ({inr(t.advance_tax.tds)}) covers the estimated tax, so no advance-tax instalments (15 Jun, 15 Sep, 15 Dec, 15 Mar) are needed.</p>
                )}
              </Card>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title={`${t.year === "2025-26" ? "Section 80C" : "Section 123 (was 80C)"} — investments that cut tax`} description="Only counts under the old regime.">
              {(() => {
                const used = Math.min(100, (t.section_80c.total / t.section_80c.limit) * 100);
                const full = t.section_80c.total >= t.section_80c.limit;
                return (
                  <div>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className="font-medium">{inr(Math.min(t.section_80c.total, t.section_80c.limit))} of the {inr(t.section_80c.limit)} limit used</span>
                      {full && <span className="flex items-center gap-1 text-xs text-[var(--good-text)]"><CircleCheck className="size-3.5" /> Fully used</span>}
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[#dbe8f9]" role="progressbar" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100} aria-label="Section 80C limit used">
                      <div className="h-full rounded-full bg-[var(--chart-1)]" style={{ width: `${Math.max(2, used)}%` }} />
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {full ? `You invested ${inr(t.section_80c.total)} — extra investments here won't reduce tax further.` : `${inr(t.section_80c.limit - t.section_80c.total)} still available.`}
                    </div>
                  </div>
                );
              })()}
              <ul className="mt-3 divide-y divide-border text-sm">
                {t.section_80c.parts.map((p) => <li key={p.name} className="flex justify-between py-1.5"><span>{p.name}</span><span className="tabular">{inr(p.amount)}</span></li>)}
              </ul>
            </Card>
            <Card title="HRA exemption" description={`The ${t.hra.rule}.`}>
              <ul className="divide-y divide-border text-sm">
                <li className="flex justify-between py-1.5"><span>HRA received</span><span className="tabular">{inr(t.hra.received)}</span></li>
                <li className="flex justify-between gap-2 py-1.5"><span>Rent paid {t.hra.rent_source === "entered" ? "(the monthly rent you entered × 12)" : t.hra.rent_source === "transactions" ? "(your payments to your landlord)" : "(none found — add your landlord in Settings → About you)"}</span><span className="tabular">{inr(t.hra.rent_paid)}</span></li>
                <li className="flex justify-between py-1.5 font-semibold"><span>Exempt from tax (old regime)</span><span className="tabular">{inr(t.hra.exempt)}</span></li>
              </ul>
              {t.headroom.length > 0 && (
                <div className="mt-3 grid gap-2">
                  {t.headroom.map((h) => (
                    <p key={h.section} className="flex gap-2 rounded-lg bg-muted p-2 text-sm"><Lightbulb className="mt-0.5 size-4 shrink-0 text-[var(--warning)]" />{h.tip}</p>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <Card className="mt-4" title="Evidence from your transactions" description="What FinPilot counted, so you can check it. Click a row to see the payments.">
            <ul className="divide-y divide-border">
              {t.evidence.filter((e) => e.amount > 0 || e.projected > 0).map((e) => (
                <li key={e.label}>
                  <button type="button" className="flex w-full items-center gap-3 py-2 text-left text-sm" onClick={() => setOpen(open === e.label ? null : e.label)} aria-expanded={open === e.label}>
                    <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", open === e.label && "rotate-180")} />
                    <span className="flex-1">{e.label} <span className="text-xs text-muted-foreground">· {e.items.length} payments</span></span>
                    <span className="tabular font-medium">{inr(e.amount)}</span>
                    {e.projected > 0 && <span className="hidden w-36 text-right text-xs text-muted-foreground tabular sm:inline">+ {inr(e.projected)} scheduled</span>}
                  </button>
                  {open === e.label && (
                    <ul className="mb-2 ml-7 grid gap-0.5 text-xs text-muted-foreground">
                      {e.items.map((i) => <li key={i.id} className="flex justify-between"><span>{fmtDate(i.date)} · {i.merchant}</span><span className="tabular">{inr(i.amount)}</span></li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="mt-4" title="Your salary details" description="From your Form 16 or payslips. Used for both years; later years are scaled by the change in your salary credits.">
            <ProfileForm key={JSON.stringify(t.profile)} profile={t.profile} onSaved={() => qc.invalidateQueries({ queryKey: ["tax"] })} />
          </Card>

          <div className="mt-4 flex gap-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            <span>{t.disclaimer}{t.year === "2026-27" && " The Income-tax Act, 2025 renumbers sections; the familiar names are shown so they match your payslips and Form 16."}</span>
          </div>
        </>
      )}
    </>
  );
}
