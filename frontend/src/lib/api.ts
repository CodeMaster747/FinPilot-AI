// Thin fetch wrapper for the same-origin FastAPI backend.
// - cookies carry the session (httpOnly), so no tokens live in JS
// - every mutating request sends X-Requested-With (the backend's CSRF guard)
// - a 401 triggers one silent refresh, then a redirect to /login

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; params?: Record<string, unknown>; noRedirect?: boolean };

const BASE = "/api/v1";
let refreshing: Promise<boolean> | null = null;

function buildUrl(path: string, params?: Record<string, unknown>) {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(BASE + "/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-Requested-With": "finpilot" },
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshing = null), 0);
      });
  }
  return refreshing;
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { body, params, noRedirect, headers, ...rest } = opts;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const init: RequestInit = {
    credentials: "same-origin",
    ...rest,
    headers: {
      "X-Requested-With": "finpilot",
      ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
      ...(headers || {}),
    },
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  };
  let res = await fetch(buildUrl(path, params), init);
  if (res.status === 401 && !path.startsWith("/auth/")) {
    if (await refreshSession()) res = await fetch(buildUrl(path, params), init);
  }
  if (res.status === 401 && !noRedirect && !path.startsWith("/auth/")) {
    // A full page load (not the router) on purpose: it also drops every cached query of the old session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login/";
    throw new ApiError(401, "Not signed in");
  }
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
