"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ServerProblem } from "@/components/server-problem";
import { api, ApiError } from "@/lib/api";
import { isNative, loadNativeState, serverUrl } from "@/lib/platform";

// Entry point: the phone app first needs a server; then signed-in users go to the dashboard, everyone else to sign-in.
export default function Home() {
  const router = useRouter();
  const [problem, setProblem] = useState<string | null>(null);

  // Resolves to a "can't reach the server" message, or null once it has navigated away.
  const start = useCallback(async (): Promise<string | null> => {
    try {
      await loadNativeState();
    } catch (e) {
      return `FinPilot couldn't read its saved settings on this phone (${(e as Error).message}).`;
    }
    if (isNative() && !serverUrl()) {
      router.replace("/connect/");
      return null;
    }
    try {
      await api("/auth/me", { noRedirect: true });
      router.replace("/dashboard/");
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) return e.message;
      router.replace("/login/");
    }
    return null;
  }, [router]);

  useEffect(() => {
    let cancelled = false;
    start().then((p) => { if (!cancelled) setProblem(p); });
    return () => { cancelled = true; };
  }, [start]);

  if (problem) return <ServerProblem message={problem} onRetry={() => { setProblem(null); start().then(setProblem); }} />;
  return <div className="flex min-h-dvh items-center justify-center text-sm text-muted-foreground">Loading FinPilot AI…</div>;
}
