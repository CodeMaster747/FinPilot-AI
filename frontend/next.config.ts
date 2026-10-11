import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Production builds are a static export served by the FastAPI backend (one origin, no Node at runtime).
// `next dev` proxies /api to a locally running backend so the UI can be developed with hot reload.
export default function config(phase: string): NextConfig {
  const dev = phase === PHASE_DEVELOPMENT_SERVER;
  const base: NextConfig = {
    trailingSlash: true,
    images: { unoptimized: true },
    devIndicators: false,
    turbopack: {
      rules: {
        "*.css": { loaders: ["@tailwindcss/turbopack"], as: "*.css" },
      },
    },
  };
  if (dev) {
    const api = process.env.FINPILOT_API ?? "http://127.0.0.1:8000";
    return { ...base, async rewrites() { return [{ source: "/api/:path*", destination: `${api}/api/:path*` }]; } };
  }
  return { ...base, output: "export" };
}
