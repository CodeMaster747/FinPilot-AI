"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, authEvents } from "@/lib/api";
import { isNative } from "@/lib/platform";

const TOP_LEVEL = ["/", "/dashboard/", "/login/", "/connect/", "/onboarding/"];

/** Session expiry and, in the Android app, the hardware back button. */
function AppEvents() {
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();

  useEffect(() => {
    const events = authEvents;
    if (!events) return;
    const onSignedOut = () => {
      qc.clear();
      router.replace("/login/");
    };
    events.addEventListener("signed-out", onSignedOut);
    return () => events.removeEventListener("signed-out", onSignedOut);
  }, [qc, router]);

  useEffect(() => {
    if (!isNative()) return;
    let remove: (() => void) | undefined;
    import("@capacitor/app").then(({ App }) => {
      const handle = App.addListener("backButton", () => {
        // An open dialog or side sheet closes first (Escape is what they listen for), then the page goes back.
        const dialog = document.querySelector('[role="dialog"], [role="alertdialog"]');
        if (dialog) {
          (document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
          return;
        }
        if (TOP_LEVEL.includes(window.location.pathname)) App.minimizeApp();
        else router.back();
      });
      remove = () => void handle.then((h) => h.remove());
    });
    return () => remove?.();
  }, [router, pathname]);

  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            // don't hammer an unreachable server; one retry for everything else
            retry: (count, error) => !(error instanceof ApiError && [0, 401, 403, 404].includes(error.status)) && count < 1,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <AppEvents />
        {children}
        <Toaster richColors position="top-center" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
