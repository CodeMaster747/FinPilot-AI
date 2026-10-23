"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CircleCheck, FileUp, Lock, ScanLine, ShieldCheck, Smartphone } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConsentDialog, ICON, ImportDialog, type Kind, MailboxPanel, SmsPhoneSync, StatusPill, useRefresh } from "@/components/sources";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { get, patch, put } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { isNative } from "@/lib/platform";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = ["Welcome", "About you", "Bank SMS", "Email", "Done"];

function num(v: string): number | null {
  const n = Number(v.replace(/[,\s₹]/g, ""));
  return v.trim() && Number.isFinite(n) && n > 0 ? n : null;
}

function AboutYou({ onNext }: { onNext: () => void }) {
  const me = useMe();
  const refresh = useRefresh();
  const prefs = me.data?.preferences ?? {};
  const [f, setF] = useState({
    take_home: prefs.take_home_monthly ? String(prefs.take_home_monthly) : "", payday: prefs.payday ? String(prefs.payday) : "",
    rent: prefs.rent_monthly ? String(prefs.rent_monthly) : "", rent_day: prefs.rent_day ? String(prefs.rent_day) : "",
    landlord: (prefs.rent_payee as string) ?? "", city: "",
  });
  const save = useMutation({
    mutationFn: async () => {
      const day = (v: string) => { const n = Number(v); return n >= 1 && n <= 31 ? Math.round(n) : null; };
      await patch("/auth/me", { preferences: {
        take_home_monthly: num(f.take_home), payday: day(f.payday), rent_monthly: num(f.rent), rent_day: day(f.rent_day),
        rent_payee: f.landlord.trim().length >= 2 ? f.landlord.trim() : null,
      } });
      if (f.city.trim()) await put("/tax/profile", { city: f.city.trim() });
    },
    onSuccess: () => { refresh(); onNext(); },
    onError: (e) => toast.error((e as Error).message),
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <form className="grid gap-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div>
        <h2 className="text-xl font-semibold">A few facts about you <span className="text-sm font-normal text-muted-foreground">(optional)</span></h2>
        <p className="mt-1 text-sm text-muted-foreground">
          FinPilot learns your salary and rent from your bank messages, but that takes a few months. With these it can plan for you from day one. Skip anything you prefer not to share.
        </p>
      </div>
      <div className="grid gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">Take-home pay per month (₹)<Input inputMode="numeric" value={f.take_home} onChange={set("take_home")} placeholder="e.g. 65000" /></label>
        <label className="grid gap-1 text-sm">Usually paid on day<Input inputMode="numeric" value={f.payday} onChange={set("payday")} placeholder="e.g. 1" /></label>
        <label className="grid gap-1 text-sm">Rent per month (₹)<Input inputMode="numeric" value={f.rent} onChange={set("rent")} placeholder="leave empty if none" /></label>
        <label className="grid gap-1 text-sm">Rent paid on day<Input inputMode="numeric" value={f.rent_day} onChange={set("rent_day")} placeholder="e.g. 5" /></label>
        <label className="grid gap-1 text-sm sm:col-span-2">Landlord&apos;s name or UPI ID (so rent payments are recognised)
          <Input value={f.landlord} onChange={set("landlord")} placeholder="e.g. Ramesh Kumar or ramesh@okaxis" />
        </label>
        <label className="grid gap-1 text-sm sm:col-span-2">City (for the HRA part of your tax estimate)<Input value={f.city} onChange={set("city")} placeholder="e.g. Chennai" /></label>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onNext}>Skip</Button>
        <Button type="submit" disabled={save.isPending}>Save and continue <ArrowRight /></Button>
      </div>
    </form>
  );
}

function SourceStep({ kind, source, onNext }: { kind: Kind; source?: Source; onNext: () => void }) {
  const [consent, setConsent] = useState(false);
  const [importing, setImporting] = useState(false);
  const [granted, setGranted] = useState(false);
  const Icon = ICON[kind];
  const active = source?.status === "active";
  const native = isNative();
  return (
    <div className="grid gap-5">
      <div className="flex items-start gap-3">
        <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-secondary text-secondary-foreground"><Icon className="size-5" /></div>
        <div className="flex-1">
          <h2 className="text-xl font-semibold">{kind === "sms" ? "Bank & payment SMS" : "Receipts & bank emails"}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {kind === "sms"
              ? "Every card swipe, UPI payment, salary credit and bill reminder already arrives as an SMS. FinPilot turns them into your transaction history — no bank login needed."
              : "Bank alerts, order receipts (with line items), bills, statements and subscription emails fill in what SMS leave out."}
          </p>
        </div>
        {source && <StatusPill status={source.status} />}
      </div>
      {!active ? (
        <div className="grid gap-3 rounded-xl border border-border bg-card p-4">
          <div className="flex items-start gap-2 text-sm text-muted-foreground"><Lock className="mt-0.5 size-4 shrink-0" />
            Nothing is read until you allow it. You&apos;ll see exactly what is read, what is stored and for how long.</div>
          {kind === "sms" && !native && (
            <div className="flex items-start gap-2 rounded-lg bg-muted p-3 text-sm"><Smartphone className="mt-0.5 size-4 shrink-0" />
              <span>Reading SMS needs the FinPilot Android app. You can allow it now and finish on your phone, or import an SMS backup file.</span></div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setConsent(true)}><ShieldCheck /> Review and allow</Button>
            <Button variant="ghost" onClick={onNext}>Skip this</Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-3 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-[var(--good-text)]"><CircleCheck className="size-4" /> Allowed.</div>
          {kind === "sms" && native && <SmsPhoneSync source={source} autoStart={granted} />}
          {kind === "sms" && !native && (
            <p className="text-sm text-muted-foreground">Open the FinPilot app on your Android phone and sign in with this account — it reads your SMS from there. Or import a file:</p>
          )}
          {kind === "email" && <MailboxPanel source={source} />}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button variant="outline" onClick={() => setImporting(true)}><FileUp /> Import a file instead</Button>
            <Button onClick={onNext}>Continue <ArrowRight /></Button>
          </div>
        </div>
      )}
      <ConsentDialog kind={kind} open={consent} onOpenChange={setConsent} onGranted={() => setGranted(true)} />
      <ImportDialog kind={kind} open={importing} onOpenChange={setImporting} />
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const [step, setStep] = useState(0);
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => get<{ sources: Source[] }>("/sources") });
  const finish = useMutation({
    mutationFn: () => patch("/auth/me", { onboarded: true }),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["me"] }); router.replace("/dashboard/"); },
  });
  const byKind = (k: Kind) => sources.data?.sources.find((s) => s.kind === k);
  const connected = (sources.data?.sources ?? []).filter((s) => s.status === "active");
  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto grid max-w-2xl gap-8 px-4 pt-[max(2.5rem,var(--sa-top))] pb-[max(2.5rem,var(--sa-bottom))]">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-base font-semibold"><span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground"><CircleCheck className="size-4" /></span>FinPilot AI</span>
          {step < STEPS.length - 1 && <Button variant="ghost" size="sm" onClick={() => finish.mutate()}>Skip setup</Button>}
        </div>
        <ol className="grid grid-cols-5 gap-2" aria-label="Setup steps">
          {STEPS.map((s, i) => (
            <li key={s} className="grid gap-1.5">
              <div className={cn("h-1 rounded-full", i <= step ? "bg-primary" : "bg-border")} />
              <span className={cn("text-[11px] sm:text-xs", i === step ? "font-medium text-foreground" : "text-muted-foreground")}>{s}</span>
            </li>
          ))}
        </ol>
        {step === 0 && (
          <div className="grid gap-5">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Welcome{me.data ? `, ${me.data.name.split(" ")[0]}` : ""}!</h1>
              <p className="mt-2 text-muted-foreground">FinPilot builds your financial picture from the messages you already get — but only from the sources you allow, one at a time.</p>
            </div>
            <ul className="grid gap-3 text-sm">
              {[[ShieldCheck, "You decide, per source", "Allow SMS and email separately, and pause, revoke or delete at any time."],
                [Lock, "Stays on your own server", "Everything is processed by the FinPilot server on your laptop. Chats, OTPs and promotions are dropped before they're stored, and message text is deleted after 90 days."],
                [ScanLine, "Uploads are optional", "Prefer not to connect anything? Scan receipts, import a bank statement or add payments by hand."]].map(([I, t, d]) => {
                const IconC = I as typeof Lock;
                return (
                  <li key={t as string} className="flex gap-3 rounded-xl border border-border bg-card p-3">
                    <IconC className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span><span className="block font-medium">{t as string}</span><span className="text-muted-foreground">{d as string}</span></span>
                  </li>
                );
              })}
            </ul>
            <div className="flex justify-end"><Button onClick={() => setStep(1)}>Get started <ArrowRight /></Button></div>
          </div>
        )}
        {step === 1 && <AboutYou onNext={() => setStep(2)} />}
        {step === 2 && <SourceStep kind="sms" source={byKind("sms")} onNext={() => setStep(3)} />}
        {step === 3 && <SourceStep kind="email" source={byKind("email")} onNext={() => setStep(4)} />}
        {step === 4 && (
          <div className="grid gap-5">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{connected.length ? "You're set up" : "You can connect sources any time"}</h1>
              <p className="mt-2 text-muted-foreground">
                {connected.length
                  ? `Connected: ${connected.map((s) => s.title).join(" and ")}. Your forecast, subscriptions and insights are being prepared — it takes a few seconds.`
                  : "Nothing is connected yet. You can still scan receipts, import statements or add payments by hand, and connect SMS or email later from Connections."}
              </p>
            </div>
            <div className="flex justify-end"><Button onClick={() => finish.mutate()} disabled={finish.isPending}>Go to my dashboard <ArrowRight /></Button></div>
          </div>
        )}
      </div>
    </div>
  );
}
