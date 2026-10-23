// Files from the API (CSV/PDF/JSON exports, receipt images). A browser saves them with a normal download; the Android
// app can't, so it writes the file to app storage and opens Android's share sheet (save to Files, Drive, WhatsApp…).

"use client";

import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { isNative } from "@/lib/platform";

function filenameFrom(disposition: string | null, fallback: string): string {
  const m = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return m ? decodeURIComponent(m[1]) : fallback;
}

function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export async function downloadFile(path: string, params?: Record<string, unknown>, fallbackName = "finpilot-download"): Promise<void> {
  const res = await apiFetch(path, { params, timeoutMs: 120_000 });
  if (!res.ok) {
    let message = `Download failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") message = data.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  const blob = await res.blob();
  const name = filenameFrom(res.headers.get("content-disposition"), fallbackName);
  if (isNative()) {
    const { Filesystem, Directory } = await import("@capacitor/filesystem");
    const { Share } = await import("@capacitor/share");
    const written = await Filesystem.writeFile({ path: name, data: await toBase64(blob), directory: Directory.Cache });
    await Share.share({ title: name, files: [written.uri], dialogTitle: `Save or share ${name}` });
    return;
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** An object URL for an image the API serves only to the signed-in user (works with cookies and Bearer tokens). */
export function useApiBlobUrl(path: string | null): string | null {
  const [loaded, setLoaded] = useState<{ path: string; url: string } | null>(null);
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    let made: string | null = null;
    const apiPath = path.startsWith("/api/v1") ? path.slice("/api/v1".length) : path;
    apiFetch(apiPath)
      .then((res) => (res.ok ? res.blob() : null))
      .then((blob) => {
        if (blob && !cancelled) {
          made = URL.createObjectURL(blob);
          setLoaded({ path, url: made });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      if (made) URL.revokeObjectURL(made);
    };
  }, [path]);
  return path && loaded?.path === path ? loaded.url : null;
}
