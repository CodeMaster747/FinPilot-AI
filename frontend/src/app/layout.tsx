import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "./globals.css";

import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "FinPilot AI",
  description: "Privacy-first personal finance: consented SMS & email capture, forecasting and affordable picks.",
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
