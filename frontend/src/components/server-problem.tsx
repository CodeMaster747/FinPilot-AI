"use client";

import Link from "next/link";
import { RefreshCw, ServerOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { isNative } from "@/lib/platform";

/** Shown when the FinPilot server can't be reached (laptop off, different network, tunnel address changed). */
export function ServerProblem({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="grid max-w-sm gap-4 text-center">
        <ServerOff className="mx-auto size-10 text-muted-foreground" aria-hidden />
        <h1 className="text-xl font-semibold">Can&apos;t reach your FinPilot server</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
        <div className="flex flex-col gap-2">
          <Button onClick={onRetry}><RefreshCw /> Try again</Button>
          {isNative() && <Button variant="outline" render={<Link href="/connect/" />}>Change server address</Button>}
        </div>
      </div>
    </div>
  );
}
