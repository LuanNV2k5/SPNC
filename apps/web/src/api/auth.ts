import { ApiError, fromBody, newRequestId } from "./errors";

/**
 * Tokens (docs/46 D7): the access token lives in memory only, the refresh token in
 * localStorage. Rotation is single-flight across tabs: the server revokes the whole token
 * family when a rotated token is presented again (F3), so two tabs must never rotate the
 * same token. Inside the Web Lock the current refresh token is re-read from storage, so every
 * rotation uses the newest one.
 */

const REFRESH_KEY = "spnc.refresh_token";
const LOCK_NAME = "spnc-auth-refresh";
export const TIMEOUT_MS = 30_000;

let accessToken: string | null = null;
let inTab: Promise<boolean> | null = null;
const listeners = new Set<(loggedIn: boolean) => void>();

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

function writeRefresh(token: string | null): void {
  try {
    if (token) localStorage.setItem(REFRESH_KEY, token);
    else localStorage.removeItem(REFRESH_KEY);
  } catch {
    // Storage unavailable (private mode): the session lasts until the tab closes
  }
}

export const getAccessToken = () => accessToken;
export const hasRefreshToken = () => readRefresh() !== null;

/** Called with false when tokens are gone (logout here or in another tab, revoked family). */
export function onAuthChange(fn: (loggedIn: boolean) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function setTokens(access: string | null, refresh: string | null): void {
  accessToken = access;
  writeRefresh(refresh);
  listeners.forEach((fn) => fn(access !== null));
}

export function clearTokens(): void {
  setTokens(null, null);
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === REFRESH_KEY && e.newValue === null && accessToken) {
      accessToken = null;
      listeners.forEach((fn) => fn(false));
    }
  });
}

/** fetch for the auth endpoints themselves: no Authorization retry loop, errors as ApiError. */
export async function rawJson<T>(path: string, init: RequestInit & { auth?: boolean } = {}): Promise<T> {
  const requestId = newRequestId();
  const headers = new Headers(init.headers);
  headers.set("X-Request-ID", requestId);
  if (init.auth && accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (err) {
    throw new ApiError(null, "NETWORK_ERROR", err instanceof Error ? err.message : String(err), requestId);
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw fromBody(res.status, body, res.headers.get("X-Request-ID") ?? requestId);
  return body as T;
}

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export async function login(username: string, password: string): Promise<void> {
  const form = new URLSearchParams({ username, password, grant_type: "password" });
  const t = await rawJson<TokenPair>("/api/v1/auth/login", {
    method: "POST",
    body: form,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  setTokens(t.access_token, t.refresh_token);
}

async function withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  return locks ? locks.request(LOCK_NAME, fn) : fn();
}

async function rotate(): Promise<boolean> {
  return withRefreshLock(async () => {
    const current = readRefresh();
    if (!current) return false;
    try {
      const t = await rawJson<TokenPair>("/api/v1/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refresh_token: current }),
        headers: { "Content-Type": "application/json" },
      });
      setTokens(t.access_token, t.refresh_token);
      return true;
    } catch (err) {
      // A network failure keeps the refresh token for a later attempt; a rejection ends the session
      if (err instanceof ApiError && err.status !== null && err.status < 500) clearTokens();
      if (err instanceof ApiError && err.status === null) throw err;
      return false;
    }
  });
}

/** Obtains a new access token. Concurrent callers in this tab share one rotation. */
export function refreshAccessToken(): Promise<boolean> {
  if (!inTab) inTab = rotate().finally(() => (inTab = null));
  return inTab;
}

export async function logout(): Promise<void> {
  const refresh = readRefresh();
  try {
    if (refresh && accessToken) {
      await rawJson("/api/v1/auth/logout", {
        method: "POST",
        auth: true,
        body: JSON.stringify({ refresh_token: refresh }),
        headers: { "Content-Type": "application/json" },
      });
    }
  } catch {
    // Logging out locally matters more than the server call
  } finally {
    clearTokens();
  }
}
