// Where the UI runs: in a browser (served by the FinPilot server itself) or inside the FinPilot Android app
// (bundled in the APK, talking to the server on your laptop). The app keeps the server address and its sign-in
// tokens in Android's app storage (Capacitor Preferences).

import { Capacitor } from "@capacitor/core";
// Imported statically on purpose: a Capacitor plugin is a Proxy, and returning one from an async function makes the
// promise call its `.then`, which the proxy treats as a native method ("Preferences.then() is not implemented").
import { Preferences } from "@capacitor/preferences";

export function isNative(): boolean {
  return typeof window !== "undefined" && Capacitor.isNativePlatform();
}

type NativeState = { server: string | null; access: string | null; refresh: string | null };
const state: NativeState = { server: null, access: null, refresh: null };
let loading: Promise<void> | null = null;
const KEYS = { server: "fp.server", access: "fp.access", refresh: "fp.refresh" } as const;

/** Loads the saved server address and tokens once; every API call waits for it on the phone. */
export function loadNativeState(): Promise<void> {
  if (!isNative()) return Promise.resolve();
  if (!loading) {
    loading = (async () => {
      const [server, access, refresh] = await Promise.all(
        [Preferences.get({ key: KEYS.server }), Preferences.get({ key: KEYS.access }), Preferences.get({ key: KEYS.refresh })]);
      state.server = server.value;
      state.access = access.value;
      state.refresh = refresh.value;
    })().catch((e) => {
      loading = null; // let the next call try again
      throw e;
    });
  }
  return loading;
}

export function serverUrl(): string | null {
  return state.server;
}

export function accessToken(): string | null {
  return state.access;
}

export function refreshToken(): string | null {
  return state.refresh;
}

/** "192.168.1.5:8000" → "http://192.168.1.5:8000"; drops trailing slashes and any path. */
export function normalizeServer(input: string): string {
  let value = input.trim();
  if (!value) return "";
  if (!/^https?:\/\//i.test(value)) value = `http://${value}`;
  try {
    const url = new URL(value);
    return `${url.protocol}//${url.host}`;
  } catch {
    return "";
  }
}

export async function setServerUrl(url: string | null): Promise<void> {
  state.server = url;
  if (url) await Preferences.set({ key: KEYS.server, value: url });
  else await Preferences.remove({ key: KEYS.server });
}

export async function setTokens(tokens: { access_token: string; refresh_token: string }): Promise<void> {
  state.access = tokens.access_token;
  state.refresh = tokens.refresh_token;
  if (!isNative()) return;
  await Promise.all([Preferences.set({ key: KEYS.access, value: tokens.access_token }), Preferences.set({ key: KEYS.refresh, value: tokens.refresh_token })]);
}

export async function clearTokens(): Promise<void> {
  state.access = null;
  state.refresh = null;
  if (!isNative()) return;
  await Promise.all([Preferences.remove({ key: KEYS.access }), Preferences.remove({ key: KEYS.refresh })]);
}

/** Small key/value storage for app-only conveniences (e.g. when SMS were last synced). */
export async function getPref(key: string): Promise<string | null> {
  if (!isNative()) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }
  return (await Preferences.get({ key })).value;
}

export async function setPref(key: string, value: string): Promise<void> {
  if (!isNative()) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* storage unavailable: a convenience only */
    }
    return;
  }
  await Preferences.set({ key, value });
}
