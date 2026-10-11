"use client";

import {
  ArrowLeftRight, Banknote, Bike, Briefcase, Car, CircleHelp, Clapperboard, Coins, CreditCard, Dumbbell, Fuel, GraduationCap,
  HeartPulse, House, Landmark, Laptop, type LucideIcon, Mail, MessageSquareText, Percent, Plane, Receipt, Repeat, Shield, Shirt,
  ShoppingBag, ShoppingBasket, Sparkles, TrendingUp, Upload, Utensils, Wifi, Zap,
} from "lucide-react";

import { inr } from "@/lib/format";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  briefcase: Briefcase, percent: Percent, coins: Coins, house: House, "shopping-basket": ShoppingBasket, zap: Zap, wifi: Wifi,
  landmark: Landmark, shield: Shield, "heart-pulse": HeartPulse, car: Car, fuel: Fuel, "graduation-cap": GraduationCap,
  banknote: Banknote, receipt: Receipt, utensils: Utensils, bike: Bike, "shopping-bag": ShoppingBag, laptop: Laptop, shirt: Shirt,
  dumbbell: Dumbbell, clapperboard: Clapperboard, repeat: Repeat, sparkles: Sparkles, plane: Plane, "trending-up": TrendingUp,
  "arrow-left-right": ArrowLeftRight, "credit-card": CreditCard, "circle-help": CircleHelp,
};

export function CategoryIcon({ icon, className }: { icon?: string | null; className?: string }) {
  const Icon = (icon && ICONS[icon]) || CircleHelp;
  return <Icon className={cn("size-4", className)} aria-hidden />;
}

export function OriginIcon({ origin, className }: { origin: string; className?: string }) {
  const Icon = origin === "sms" ? MessageSquareText : origin === "email" ? Mail : origin === "receipt" ? Receipt : Upload;
  return <Icon className={cn("size-3.5", className)} aria-label={origin} />;
}

export function Amount({ value, direction, className, decimals = true }: { value: number; direction: "debit" | "credit"; className?: string; decimals?: boolean }) {
  const credit = direction === "credit";
  return (
    <span className={cn("tabular font-medium", credit && "text-[var(--good-text)]", className)}>
      {credit ? "+" : "−"}{inr(value, { decimals }).replace("−", "")}
    </span>
  );
}

export function StatTile({ label, value, sub, tone, icon: Icon }: { label: string; value: string; sub?: React.ReactNode; tone?: "good" | "warn" | "bad"; icon?: LucideIcon }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {Icon && <Icon className="size-4" aria-hidden />}{label}
      </div>
      <div className="mt-1 text-2xl font-semibold tracking-tight">{value}</div>
      {sub && (
        <div className={cn("mt-1 text-xs text-muted-foreground", tone === "good" && "text-[var(--good-text)]", tone === "bad" && "text-[var(--critical)]")}>{sub}</div>
      )}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children, action }: { icon?: LucideIcon; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card px-6 py-12 text-center">
      {Icon && <Icon className="mb-3 size-8 text-muted-foreground" aria-hidden />}
      <div className="font-medium">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Card({ title, description, action, children, className }: { title?: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-xl border border-border bg-card p-4 md:p-5", className)}>
      {(title || action) && (
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function NativeSelect({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cn("h-8 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50", className)}>
      {children}
    </select>
  );
}

export function Pill({ children, tone = "neutral", className }: { children: React.ReactNode; tone?: "neutral" | "blue" | "good" | "warn" | "bad"; className?: string }) {
  const tones = {
    neutral: "bg-muted text-muted-foreground",
    blue: "bg-secondary text-secondary-foreground",
    good: "bg-[#e7f5e7] text-[var(--good-text)]",
    warn: "bg-[#fdf2d6] text-[#7a5200]",
    bad: "bg-[#fbe4e4] text-[#a32525]",
  };
  return <span className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}

export const fmtMoney = inr;
