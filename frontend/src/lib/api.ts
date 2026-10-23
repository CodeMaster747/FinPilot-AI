// Fetch wrapper for the FinPilot API.
// - In a browser the UI is served by the FinPilot server itself: same origin, httpOnly session cookies, and every
//   request carries X-Requested-With (the server's CSRF guard).
// - In the Android app the UI is bundled in the APK and talks to the server on your laptop: an absolute URL, Bearer
//   tokens kept in app storage, and X-FinPilot-Client: android.
// - A 401 triggers one silent refresh; if that fails the app signs out (router navigation, never a page reload).
// - "Can't reach the server" is reported as such, not as "signed out".

import { accessToken, clearTokens, isNative, loadNativeState, refreshToken, serverUrl, setTokens } from "@/lib/platform";

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; params?: Record<string, unknown>; noRedirect?: boolean; timeoutMs?: number };
type Tokens = { access_token: string; refresh_token: string; expires_in?: number };

const PREFIX = "/api/v1";
const DEFAULT_TIMEOUT = 30_000;
let refreshing: Promise<boolean> | null = null;

/** Fired when the session can't be renewed; the app shell sends the user to the sign-in page. */
export const authEvents = typeof window !== "undefined" ? new EventTarget() : null;

export function apiUrl(path: string, params?: Record<string, unknown>): string {
  const base = isNative() ? serverUrl() : window.location.origin;
  if (!base) throw new ApiError(0, "Connect the app to your FinPilot server first.", { code: "no_server" });
  const url = new URL(PREFIX + path, base);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

function authHeaders(): Record<string, string> {
  if (!isNative()) return { "X-Requested-With": "finpilot" };
  const token = accessToken();
  return { "X-FinPilot-Client": "android", ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

function unreachable(): ApiError {
  const where = isNative() ? serverUrl() : null;
  return new ApiError(0, where
    ? `Can't reach your FinPilot server at ${where}. Make sure python3 run.py is running on your laptop and that the phone can reach it (same Wi-Fi or hotspot, or the --tunnel address).`
    : "Can't reach the FinPilot server. Check that python3 run.py is still running.", { code: "unreachable" });
}

async function send(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch {
    throw unreachable();
  } finally {
    clearTimeout(timer);
  }
}

async function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        if (isNative()) {
          const token = refreshToken();
          if (!token) return false;
          const res = await send(apiUrl("/auth/refresh"), {
            method: "POST", credentials: "omit",
            headers: { "X-FinPilot-Client": "android", "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: token }),
          }, DEFAULT_TIMEOUT);
          if (!res.ok) return false;
          await setTokens((await res.json()) as Tokens);
          return true;
        }
        const res = await send(apiUrl("/auth/refresh"), { method: "POST", credentials: "same-origin", headers: authHeaders() }, DEFAULT_TIMEOUT);
        return res.ok;
      } catch {
        return false;
      }
    })().finally(() => {
      setTimeout(() => (refreshing = null), 0);
    });
  }
  return refreshing;
}

/** A raw authenticated request (downloads, images): refreshes once on 401 and returns the Response. */
export async function apiFetch(path: string, opts: Options = {}): Promise<Response> {
  await loadNativeState();
  const { body, params, headers, timeoutMs, noRedirect, ...rest } = opts;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const build = (): RequestInit => ({
    credentials: isNative() ? "omit" : "same-origin",
    ...rest,
    headers: { ...authHeaders(), ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}), ...(headers || {}) },
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });
  const url = apiUrl(path, params);
  let res = await send(url, build(), timeoutMs ?? (isForm ? 120_000 : DEFAULT_TIMEOUT));
  if (res.status === 401 && !path.startsWith("/auth/")) {
    if (await refreshSession()) res = await send(url, build(), timeoutMs ?? DEFAULT_TIMEOUT);
  }
  if (res.status === 401 && !noRedirect && !path.startsWith("/auth/")) {
    await clearTokens();
    authEvents?.dispatchEvent(new Event("signed-out"));
    throw new ApiError(401, "Not signed in");
  }
  return res;
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const res = await apiFetch(path, opts);
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail = (data as { detail?: unknown })?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : res.statusText;
    throw new ApiError(res.status, message || `Request failed (${res.status})`, data);
  }
  return data as T;
}

function safeJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const get = <T,>(path: string, params?: Record<string, unknown>) => api<T>(path, { params });
export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: "POST", body });
export const put = <T,>(path: string, body?: unknown) => api<T>(path, { method: "PUT", body });
export const patch = <T,>(path: string, body?: unknown) => api<T>(path, { method: "PATCH", body });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

/** Sign in, register or open the demo; on the phone the tokens come back in the body and are stored. */
export async function startSession<T>(path: "/auth/login" | "/auth/register" | "/auth/demo", body?: unknown): Promise<T> {
  const data = await api<T & Partial<Tokens>>(path, { method: "POST", body, noRedirect: true });
  if (isNative() && data.access_token && data.refresh_token) {
    await setTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
  }
  return data;
}

export async function endSession(): Promise<void> {
  const token = refreshToken();
  await api("/auth/logout", { method: "POST", noRedirect: true, body: isNative() && token ? { refresh_token: token } : undefined }).catch(() => null);
  await clearTokens();
}
