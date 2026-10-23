import type { Metadata, Viewport } from "next";
import "@fontsource-variable/inter";
import "./globals.css";

import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "FinPilot AI",
  description: "Privacy-first personal finance from your own bank SMS and email: transactions, forecasts, budgets, tax and a wishlist you can afford.",
};

// viewport-fit=cover lets the Android app draw edge to edge; the layout pads itself with the safe-area variables in globals.css.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f6f6f3",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
