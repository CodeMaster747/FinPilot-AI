"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";

// Entry point: send signed-in users to the dashboard, everyone else to the login page.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    api("/auth/me", { noRedirect: true })
      .then(() => router.replace("/dashboard/"))
      .catch(() => router.replace("/login/"));
  }, [router]);
  return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading FinPilot AI…</div>;
}
