"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LoaderCircle } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { useMe } from "@/lib/hooks";

// Every signed-in page: session check, first-run onboarding redirect, then the shell.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (me.isError) router.replace("/login/");
    else if (me.data && !me.data.onboarded && !pathname.startsWith("/onboarding")) router.replace("/onboarding/");
  }, [me.isError, me.data, pathname, router]);

  if (!me.data) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (pathname.startsWith("/onboarding")) return <>{children}</>;
  return <AppShell user={me.data}>{children}</AppShell>;
}
