"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FlaskConical, LoaderCircle } from "lucide-react";

import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, startSession } from "@/lib/api";
import { useSystemStatus } from "@/lib/hooks";
import { isNative, loadNativeState, serverUrl } from "@/lib/platform";

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const status = useSystemStatus(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"demo" | "login" | null>(null);
  const [server, setServer] = useState<string | null>(null);
  const ready = status.data?.demo_ready ?? false;
  const boot = status.data?.bootstrap;

  useEffect(() => {
    loadNativeState().then(() => {
      if (isNative() && !serverUrl()) router.replace("/connect/");
      setServer(serverUrl());
    });
  }, [router]);

  async function go(path: "/auth/login" | "/auth/demo", body?: unknown, kind: "demo" | "login" = "login") {
    setBusy(kind);
    setError(null);
    try {
      await startSession(path, body);
      qc.clear();
      router.replace("/dashboard/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong");
      setBusy(null);
    }
  }

  return (
    <AuthLayout>
      <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
      <p className="mt-1 text-sm text-muted-foreground">Use your FinPilot account, or create one — it takes a minute.</p>

      <form className="mt-6 grid gap-4" onSubmit={(e) => { e.preventDefault(); go("/auth/login", { email, password }); }}>
        <div className="grid gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        <Button type="submit" className="h-11" disabled={busy !== null}>
          {busy === "login" && <LoaderCircle className="animate-spin" />} Sign in
        </Button>
      </form>
      <p className="mt-4 text-sm text-muted-foreground">
        New here? <Link href="/register/" className="font-medium text-primary hover:underline">Create an account</Link>
      </p>

      <div className="my-6 flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" />for presentations<span className="h-px flex-1 bg-border" />
      </div>
      <Button variant="outline" className="h-11 w-full" disabled={!ready || busy !== null} onClick={() => go("/auth/demo", undefined, "demo")}>
        {busy === "demo" || !ready ? <LoaderCircle className="animate-spin" /> : <FlaskConical />}
        {ready ? "Explore the demo account (sample data)" : "Preparing the demo account…"}
      </Button>
      <p className="mt-2 text-xs text-muted-foreground" role="status">
        {ready
          ? "A made-up person's sample messages, clearly marked as such. It can't read your SMS or email — create your own account for that."
          : `Setting up the sample data${boot?.message ? ` — ${boot.message.toLowerCase()}` : ""}${boot?.progress ? ` (${boot.progress}%)` : ""}.`}
      </p>
      {isNative() && server && (
        <p className="mt-6 text-xs text-muted-foreground">
          Server: {server} · <Link href="/connect/" className="underline">change</Link>
        </p>
      )}
    </AuthLayout>
  );
}
