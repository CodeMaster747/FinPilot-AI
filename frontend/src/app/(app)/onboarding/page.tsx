"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CircleCheck, FileUp, Inbox, Lock, ScanLine, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { JobProgress } from "@/components/job-progress";
import { ConsentDialog, ICON, ImportDialog, type Kind, REFRESH, StatusPill } from "@/components/sources";
import { Button } from "@/components/ui/button";
import { get, patch, post } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = ["Welcome", "Bank SMS", "Emails", "Done"];

function SourceStep({ kind, source, onNext }: { kind: Kind; source?: Source; onNext: () => void }) {
  const [consent, setConsent] = useState(false);
  const [importing, setImporting] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const sample = useMutation({
    mutationFn: () => post<{ job_id: number }>(`/ingest/${kind}/sample`),
    onSuccess: (r) => setJobId(r.job_id),
    onError: (e) => toast.error((e as Error).message),
  });
  const Icon = ICON[kind];
  const active = source?.status === "active";
  return (
    <div className="grid gap-5">
      <div className="flex items-start gap-3">
        <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-secondary text-secondary-foreground"><Icon className="size-5" /></div>
        <div className="flex-1">
          <h2 className="text-xl font-semibold">{kind === "sms" ? "Bank & payment SMS" : "Receipts & bank emails"}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {kind === "sms"
              ? "Every card swipe, UPI payment, salary credit and bill reminder already arrives as an SMS. FinPilot can turn them into your transaction history — no bank login needed."
              : "Order receipts add line items to your payments, and bills, statements and subscription emails reveal what's coming up."}
          </p>
        </div>
        {source && <StatusPill status={source.status} />}
      </div>
      {!active ? (
        <div className="grid gap-3 rounded-xl border border-border bg-card p-4">
          <div className="flex items-start gap-2 text-sm text-muted-foreground"><Lock className="mt-0.5 size-4 shrink-0" />
            Nothing is read until you allow it. You&apos;ll see exactly what is read, what is stored and for how long, and you choose the purposes.</div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setConsent(true)}><ShieldCheck /> Review and allow</Button>
            <Button variant="ghost" onClick={onNext}>Skip this</Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-3 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-[var(--good-text)]"><CircleCheck className="size-4" /> Allowed. Now bring in some messages:</div>
          <div className="grid gap-2 sm:grid-cols-2">
            <button type="button" onClick={() => sample.mutate()} disabled={sample.isPending || jobId !== null}
              className="grid gap-1 rounded-lg border border-border p-3 text-left hover:bg-muted disabled:opacity-60">
              <span className="flex items-center gap-2 font-medium"><Inbox className="size-4" /> Use the sample {kind === "sms" ? "inbox" : "mailbox"}</span>
              <span className="text-xs text-muted-foreground">A realistic year of messages from the demo persona — best for trying the app.</span>
            </button>
            <button type="button" onClick={() => setImporting(true)} className="grid gap-1 rounded-lg border border-border p-3 text-left hover:bg-muted">
              <span className="flex items-center gap-2 font-medium"><FileUp className="size-4" /> Import your own file</span>
              <span className="text-xs text-muted-foreground">{kind === "sms" ? "SMS backup XML, CSV or pasted text." : ".eml or .mbox (e.g. Google Takeout)."}</span>
            </button>
          </div>
          <JobProgress jobId={jobId} invalidate={REFRESH} label="Reading messages" />
          <div className="flex justify-end"><Button onClick={onNext}>Continue <ArrowRight /></Button></div>
        </div>
      )}
      <ConsentDialog kind={kind} open={consent} onOpenChange={setConsent} />
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
    <div className="min-h-screen bg-background">
      <div className="mx-auto grid max-w-2xl gap-8 px-4 py-10">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-base font-semibold"><span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground"><CircleCheck className="size-4" /></span>FinPilot AI</span>
          {step < 3 && <Button variant="ghost" size="sm" onClick={() => finish.mutate()}>Skip setup</Button>}
        </div>
        <ol className="grid grid-cols-4 gap-2" aria-label="Setup steps">
          {STEPS.map((s, i) => (
            <li key={s} className="grid gap-1.5">
              <div className={cn("h-1 rounded-full", i <= step ? "bg-primary" : "bg-border")} />
              <span className={cn("text-xs", i === step ? "font-medium text-foreground" : "text-muted-foreground")}>{s}</span>
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
              {[[ShieldCheck, "You decide, per source", "Allow SMS and email separately, choose what they're used for, and pause, revoke or delete at any time."],
                [Lock, "Stays on this computer", "Messages are filtered, OTPs and personal chats are never stored, and the original text is deleted after 90 days."],
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
        {step === 1 && <SourceStep kind="sms" source={byKind("sms")} onNext={() => setStep(2)} />}
        {step === 2 && <SourceStep kind="email" source={byKind("email")} onNext={() => setStep(3)} />}
        {step === 3 && (
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
