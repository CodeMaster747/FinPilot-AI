"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LoaderCircle } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { ServerProblem } from "@/components/server-problem";
import { ApiError } from "@/lib/api";
import { useMe } from "@/lib/hooks";

// Every signed-in page: session check, first-run onboarding redirect, then the shell.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const pathname = usePathname();
  const unreachable = me.error instanceof ApiError && me.error.status === 0;

  useEffect(() => {
    if (me.isError && !unreachable) router.replace("/login/");
    else if (me.data && !me.data.onboarded && !pathname.startsWith("/onboarding")) router.replace("/onboarding/");
  }, [me.isError, unreachable, me.data, pathname, router]);

  if (unreachable) return <ServerProblem message={(me.error as ApiError).message} onRetry={() => me.refetch()} />;
  if (!me.data) {
    return (
      <div className="flex min-h-dvh items-center justify-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (pathname.startsWith("/onboarding")) return <>{children}</>;
  return <AppShell user={me.data}>{children}</AppShell>;
}
