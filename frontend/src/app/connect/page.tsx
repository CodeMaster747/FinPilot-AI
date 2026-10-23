"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Laptop, LoaderCircle, QrCode, Wifi } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { clearTokens, isNative, loadNativeState, normalizeServer, serverUrl, setServerUrl } from "@/lib/platform";

async function checkServer(url: string): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${url}/api/v1/health`, { signal: controller.signal, credentials: "omit" });
    const data = await res.json();
    return data?.app === "FinPilot AI" ? null : "That address answers, but it isn't a FinPilot server.";
  } catch {
    return `Nothing answered at ${url}. Check that python3 run.py is running on your laptop and that the phone is on the same Wi-Fi (or the laptop is on the phone's hotspot). On college or office Wi-Fi, start the server with python3 run.py --tunnel and use the https address it prints.`;
  } finally {
    clearTimeout(timer);
  }
}

// Pairing: the phone app needs the address of the FinPilot server running on your laptop.
export default function ConnectPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [address, setAddress] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"scan" | "connect" | null>(null);

  useEffect(() => {
    loadNativeState().then(() => {
      setCurrent(serverUrl());
      setAddress(serverUrl() ?? "");
    });
  }, []);

  async function connect(raw: string) {
    const url = normalizeServer(raw);
    if (!url) {
      setError("Enter the address shown by python3 run.py, for example http://192.168.1.5:8000");
      return;
    }
    setBusy("connect");
    setError(null);
    const problem = await checkServer(url);
    if (problem) {
      setError(problem);
      setBusy(null);
      return;
    }
    if (url !== serverUrl()) await clearTokens(); // a different server means a different account
    await setServerUrl(url);
    qc.clear();
    router.replace("/");
  }

  async function scan() {
    setBusy("scan");
    setError(null);
    try {
      const { CapacitorBarcodeScanner, CapacitorBarcodeScannerTypeHint } = await import("@capacitor/barcode-scanner");
      const result = await CapacitorBarcodeScanner.scanBarcode({
        hint: CapacitorBarcodeScannerTypeHint.QR_CODE,
        scanInstructions: "Point the camera at the QR code in the FinPilot terminal window",
      });
      const text = result.ScanResult?.trim();
      setBusy(null);
      if (text) {
        setAddress(text);
        await connect(text);
      }
    } catch {
      setBusy(null);
      setError("Couldn't scan. Allow the camera when Android asks, or type the address instead.");
    }
  }

  return (
    <div className="flex min-h-dvh items-start justify-center px-4 pt-[max(2rem,var(--sa-top))] pb-8">
      <div className="grid w-full max-w-md gap-6">
        <div className="flex items-center gap-2 text-base font-semibold">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground"><CircleCheck className="size-4" /></span>
          FinPilot AI
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Connect to your FinPilot server</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Your data is processed by the FinPilot server running on your laptop, not in the cloud. Connect this phone to it once.
          </p>
        </div>
        <ol className="grid gap-3 text-sm">
          <li className="flex gap-3 rounded-xl border border-border bg-card p-3">
            <Laptop className="mt-0.5 size-4 shrink-0 text-primary" />
            <span>On your laptop, run <code className="rounded bg-muted px-1">python3 run.py</code>. It prints a QR code and an address like <code className="rounded bg-muted px-1">http://192.168.1.5:8000</code>.</span>
          </li>
          <li className="flex gap-3 rounded-xl border border-border bg-card p-3">
            <Wifi className="mt-0.5 size-4 shrink-0 text-primary" />
            <span>Keep the phone on the same Wi-Fi, or connect the laptop to the phone&apos;s hotspot. If the network blocks devices from seeing each other (common on college Wi-Fi), run <code className="rounded bg-muted px-1">python3 run.py --tunnel</code> instead.</span>
          </li>
        </ol>
        {isNative() && (
          <Button className="h-12 text-base" onClick={scan} disabled={busy !== null}>
            {busy === "scan" ? <LoaderCircle className="animate-spin" /> : <QrCode />} Scan the QR code
          </Button>
        )}
        <form className="grid gap-2" onSubmit={(e) => { e.preventDefault(); connect(address); }}>
          <Label htmlFor="server">Or type the address</Label>
          <Input id="server" inputMode="url" autoCapitalize="off" autoCorrect="off" placeholder="http://192.168.1.5:8000"
            value={address} onChange={(e) => setAddress(e.target.value)} />
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
          <Button type="submit" variant="outline" className="h-11" disabled={busy !== null || !address.trim()}>
            {busy === "connect" && <LoaderCircle className="animate-spin" />} Connect
          </Button>
        </form>
        {current && <p className="text-xs text-muted-foreground">Currently connected to {current}.</p>}
      </div>
    </div>
  );
}
