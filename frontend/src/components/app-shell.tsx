"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CircleCheck,
  FlaskConical,
  Gauge,
  Heart,
  Inbox,
  Lightbulb,
  LoaderCircle,
  LogOut,
  Menu,
  PiggyBank,
  Plug,
  Receipt,
  Repeat,
  ScanLine,
  Settings,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { endSession, get } from "@/lib/api";
import { useSystemStatus } from "@/lib/hooks";
import { smsPermission, syncSms } from "@/lib/native/sms";
import { getPref, isNative, setPref } from "@/lib/platform";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard/", label: "Dashboard", icon: Gauge },
  { href: "/transactions/", label: "Transactions", icon: ArrowLeftRight },
  { href: "/connections/", label: "Connections", icon: Plug },
  { href: "/review/", label: "Review", icon: Inbox, badge: "review" },
  { href: "/scan/", label: "Scan a receipt", icon: ScanLine },
  { href: "/forecast/", label: "Forecast", icon: TrendingUp },
  { href: "/subscriptions/", label: "Subscriptions", icon: Repeat },
  { href: "/wishlist/", label: "Wishlist", icon: Heart },
  { href: "/smart-pick/", label: "Smart Pick", icon: Sparkles },
  { href: "/insights/", label: "Insights & coach", icon: Lightbulb },
  { href: "/budgets/", label: "Budgets & goals", icon: PiggyBank },
  { href: "/tax/", label: "Tax", icon: Receipt },
  { href: "/settings/", label: "Settings", icon: Settings },
];
const TABS = [
  { href: "/dashboard/", label: "Home", icon: Gauge },
  { href: "/transactions/", label: "Transactions", icon: ArrowLeftRight },
  { href: "/scan/", label: "Scan", icon: ScanLine },
  { href: "/smart-pick/", label: "Smart Pick", icon: Sparkles },
];

const JOB_LABELS: Record<string, string> = {
  bootstrap_demo: "Preparing the demo account",
  user_analytics: "Updating your insights",
  ingest_device: "Reading your SMS",
  imap_sync: "Reading your email",
  ingest_file: "Reading your file",
  wishlist_prices: "Checking wishlist prices",
};

export const REFRESH_KEYS = [["sources"], ["sources-history"], ["transactions"], ["dashboard"], ["review-counts"], ["review"], ["me"],
  ["accounts"], ["forecast"], ["subscriptions"], ["insights"], ["wishlist"]];

function isActive(pathname: string, href: string) {
  return pathname === href || pathname === href.slice(0, -1);
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const review = useQuery({ queryKey: ["review-counts"], queryFn: () => get<{ counts: { messages: number; transactions: number } }>("/review"),
    staleTime: 30_000 });
  const reviewCount = (review.data?.counts.messages ?? 0) + (review.data?.counts.transactions ?? 0);
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon, badge }) => (
        <Link key={href} href={href} onClick={onNavigate}
          className={cn("flex min-h-10 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            isActive(pathname, href) ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
          <Icon className="size-4 shrink-0" aria-hidden />
          <span className="flex-1">{label}</span>
          {badge === "review" && reviewCount > 0 && (
            <span className="rounded-full bg-primary px-1.5 text-[11px] font-semibold text-primary-foreground tabular">{reviewCount}</span>
          )}
        </Link>
      ))}
    </nav>
  );
}

function ActivityBanner({ userId }: { userId: number }) {
  const status = useSystemStatus();
  const jobs = (status.data?.active_jobs ?? []).filter((j) => j.user_id === userId || j.user_id === null)
    .filter((j) => JOB_LABELS[j.kind]);
  if (!jobs.length) return null;
  const j = jobs[0];
  return (
    <div role="status" className="flex items-center gap-2 border-b border-border bg-secondary px-4 py-2 text-sm text-secondary-foreground md:px-8">
      <LoaderCircle className="size-4 shrink-0 animate-spin" aria-hidden />
      <span className="font-medium">{JOB_LABELS[j.kind]}</span>
      <span className="truncate text-muted-foreground">{j.message ? `— ${j.message}` : ""} {j.progress ? `(${j.progress}%)` : ""}</span>
      {jobs.length > 1 && <span className="ml-auto hidden text-xs text-muted-foreground sm:inline">+{jobs.length - 1} more in the background</span>}
    </div>
  );
}

function DemoBanner() {
  return (
    <div role="note" className="flex items-center gap-2 border-b border-[#f3dfa6] bg-[#fefaf0] px-4 py-2 text-sm text-[#7a5200] md:px-8">
      <FlaskConical className="size-4 shrink-0" aria-hidden />
      <span><span className="font-semibold">Demo account — sample data.</span> These messages belong to a made-up person. Create your own account to use your real SMS and email.</span>
    </div>
  );
}

/** Android app: new bank SMS are read when the app opens, when it comes back to the foreground, and every minute. */
function SmsAutoSync({ userId }: { userId: number }) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!isNative()) return;
    let cancelled = false;
    const key = `fp.smsSyncedAt.${userId}`;
    const tick = async () => {
      if (cancelled || document.hidden) return;
      try {
        if ((await smsPermission())?.permission !== "granted") return;
        const r = await syncSms();
        await setPref(key, String(Date.now()));
        if (r.uploaded > 0) for (const k of REFRESH_KEYS) qc.invalidateQueries({ queryKey: k });
      } catch {
        /* the Connections page shows sync problems; background syncs stay quiet */
      }
    };
    getPref(key).then((last) => {
      if (Date.now() - Number(last || 0) > 30_000) tick();
    });
    const timer = setInterval(tick, 60_000);
    let removeListener: (() => void) | undefined;
    import("@capacitor/app").then(({ App }) => {
      const handle = App.addListener("appStateChange", ({ isActive }) => {
        if (isActive) tick();
      });
      removeListener = () => void handle.then((h) => h.remove());
    });
    return () => {
      cancelled = true;
      clearInterval(timer);
      removeListener?.();
    };
  }, [userId, qc]);
  return null;
}

export function AppShell({ user, children }: { user: User; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();

  async function logout() {
    await endSession();
    qc.clear();
    router.replace("/login/");
  }

  const brand = (
    <Link href="/dashboard/" className="flex items-center gap-2 px-3 py-1">
      <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"><CircleCheck className="size-4" /></span>
      <span className="text-base font-semibold tracking-tight">FinPilot AI</span>
    </Link>
  );
  const footer = (
    <div className="mt-auto border-t border-border px-3 pt-3 text-sm">
      <div className="truncate font-medium">{user.name}</div>
      <div className="truncate text-xs text-muted-foreground">{user.is_demo ? "Demo account (sample data)" : user.email}</div>
      <Button variant="ghost" size="sm" className="mt-2 -ml-2" onClick={logout}><LogOut /> Sign out</Button>
    </div>
  );

  return (
    <div className="flex min-h-dvh">
      {!user.is_demo && <SmsAutoSync userId={user.id} />}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-4 border-r border-border bg-sidebar p-3 md:flex">
        {brand}
        <NavLinks />
        {footer}
      </aside>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="flex w-72 flex-col gap-4 overflow-y-auto p-3 pt-[max(0.75rem,var(--sa-top))] pb-[max(0.75rem,var(--sa-bottom))]">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          {brand}
          <NavLinks onNavigate={() => setOpen(false)} />
          {footer}
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-border bg-card/95 px-2 pt-[var(--sa-top)] backdrop-blur md:hidden">
          <Button variant="ghost" size="icon" className="size-11" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu /></Button>
          <span className="font-semibold">FinPilot AI</span>
        </header>
        {user.is_demo && <DemoBanner />}
        <ActivityBanner userId={user.id} />
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 pt-5 pb-[calc(5.5rem+var(--sa-bottom))] md:px-8 md:py-8">{children}</main>
      </div>
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-card/95 pb-[var(--sa-bottom)] backdrop-blur md:hidden">
        <ul className="grid grid-cols-5">
          {TABS.map(({ href, label, icon: Icon }) => (
            <li key={href}>
              <Link href={href} className={cn("flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium",
                isActive(pathname, href) ? "text-primary" : "text-muted-foreground")}>
                <Icon className="size-5" aria-hidden />{label}
              </Link>
            </li>
          ))}
          <li>
            <button type="button" onClick={() => setOpen(true)} className="flex min-h-14 w-full flex-col items-center justify-center gap-0.5 text-[11px] font-medium text-muted-foreground">
              <Menu className="size-5" aria-hidden />More
            </button>
          </li>
        </ul>
      </nav>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
