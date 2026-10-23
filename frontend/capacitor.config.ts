import type { CapacitorConfig } from "@capacitor/cli";

// The FinPilot AI Android app: the same static UI as the web app, bundled into the APK, talking to the FinPilot server
// (python3 run.py on your laptop) over the local network or a Cloudflare tunnel.
const config: CapacitorConfig = {
  appId: "ai.finpilot.app",
  appName: "FinPilot AI",
  webDir: "out",
  server: {
    // http://localhost (not https) so the app may call a laptop at http://192.168.x.x:8000 without mixed-content blocking;
    // localhost is still a secure context for the WebView.
    androidScheme: "http",
    cleartext: true,
  },
  plugins: {
    // The UI is light-only: keep dark status/navigation bar icons even when the phone is in dark mode.
    // Insets reach CSS as --safe-area-inset-* (see globals.css); the page declares viewport-fit=cover.
    SystemBars: { style: "LIGHT", insetsHandling: "css", initialViewportFitValueHint: "cover" },
  },
};

export default config;
