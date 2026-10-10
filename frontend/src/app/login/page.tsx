"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Sparkles } from "lucide-react";

import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { useSystemStatus } from "@/lib/hooks";

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const status = useSystemStatus(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"demo" | "login" | null>(null);
  const ready = status.data?.demo_ready ?? false;
  const boot = status.data?.bootstrap;

  async function go(path: string, body?: unknown, kind: "demo" | "login" = "login") {
    setBusy(kind);
    setError(null);
    try {
      await api(path, { method: "POST", body, noRedirect: true });
      qc.clear();
      router.replace("/dashboard/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
      setBusy(null);
    }
  }

  return (
    <AuthLayout>
      <h2 className="text-2xl font-semibold tracking-tight">Welcome</h2>
      <p className="mt-1 text-sm text-muted-foreground">Explore with a ready-made demo account, or sign in to your own.</p>

      <Button className="mt-6 h-11 w-full text-base" disabled={!ready || busy !== null} onClick={() => go("/auth/demo", undefined, "demo")}>
        {busy === "demo" || !ready ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
        {ready ? "Try the demo" : "Preparing demo data…"}
      </Button>
      {!ready && (
        <p className="mt-2 text-xs text-muted-foreground" role="status">
          Setting up 24 months of sample data{boot?.message ? ` — ${boot.message.toLowerCase()}` : ""}
          {boot?.progress ? ` (${boot.progress}%)` : ""}. This takes about a minute.
        </p>
      )}

      <div className="my-6 flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" />or sign in<span className="h-px flex-1 bg-border" />
      </div>

      <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); go("/auth/login", { email, password }); }}>
        <div className="grid gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        <Button type="submit" variant="outline" className="h-10" disabled={busy !== null}>
          {busy === "login" && <LoaderCircle className="animate-spin" />} Sign in
        </Button>
      </form>
      <p className="mt-6 text-sm text-muted-foreground">
        New here? <Link href="/register/" className="font-medium text-primary hover:underline">Create an account</Link>
      </p>
    </AuthLayout>
  );
}
