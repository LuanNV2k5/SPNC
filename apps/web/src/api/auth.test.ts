import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as auth from "./auth";
import { ApiError, fromBody } from "./errors";

const KEY = "spnc.refresh_token";

/** Serializing stand-in for navigator.locks: one holder at a time, like across tabs. */
function installLocks() {
  let tail: Promise<unknown> = Promise.resolve();
  const requested: string[] = [];
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: {
      request: (name: string, fn: () => Promise<unknown>) => {
        requested.push(name);
        const run = tail.then(fn);
        tail = run.catch(() => undefined);
        return run;
      },
    },
  });
  return requested;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("refresh rotation (docs/46 D7)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let n = 0;

  beforeEach(() => {
    localStorage.clear();
    n = 0;
    fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const sent = JSON.parse(String(init.body)).refresh_token as string;
      n++;
      return json(200, { access_token: `a${n}`, refresh_token: `${sent}+`, token_type: "bearer" });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    auth.clearTokens();
  });

  it("concurrent callers in one tab share a single rotation", async () => {
    installLocks();
    localStorage.setItem(KEY, "r0");
    const results = await Promise.all([auth.refreshAccessToken(), auth.refreshAccessToken(), auth.refreshAccessToken()]);
    expect(results).toEqual([true, true, true]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(KEY)).toBe("r0+");
    expect(auth.getAccessToken()).toBe("a1");
  });

  it("every rotation uses the newest refresh token, even after another tab rotated", async () => {
    const locks = installLocks();
    localStorage.setItem(KEY, "r0");
    await auth.refreshAccessToken();
    localStorage.setItem(KEY, "other-tab"); // another tab rotated meanwhile
    await auth.refreshAccessToken();
    const sent = fetchMock.mock.calls.map(([, init]) => JSON.parse(String((init as RequestInit).body)).refresh_token);
    expect(sent).toEqual(["r0", "other-tab"]);
    expect(new Set(sent).size).toBe(sent.length); // never the same token twice
    expect(locks).toEqual(["spnc-auth-refresh", "spnc-auth-refresh"]);
  });

  it("a rejected refresh token ends the session", async () => {
    installLocks();
    localStorage.setItem(KEY, "r0");
    fetchMock.mockResolvedValueOnce(json(401, { error_code: "REFRESH_REVOKED", message: "x", request_id: "rid" }));
    const seen: boolean[] = [];
    const off = auth.onAuthChange((v) => seen.push(v));
    expect(await auth.refreshAccessToken()).toBe(false);
    expect(localStorage.getItem(KEY)).toBeNull();
    expect(seen).toEqual([false]);
    off();
  });

  it("a network failure keeps the refresh token for a later attempt", async () => {
    installLocks();
    localStorage.setItem(KEY, "r0");
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(auth.refreshAccessToken()).rejects.toMatchObject({ errorCode: "NETWORK_ERROR" });
    expect(localStorage.getItem(KEY)).toBe("r0");
  });

  it("sends a client X-Request-ID on every call", async () => {
    installLocks();
    localStorage.setItem(KEY, "r0");
    await auth.refreshAccessToken();
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Headers;
    expect(headers.get("X-Request-ID")).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe("error mapping (PROJECT_RULES #29)", () => {
  it("keeps error_code, message and request_id of the project shape", () => {
    const e = fromBody(409, { error_code: "TRACE_SEQUENCE_CONFLICT", message: "m", request_id: "r-1" }, "fallback");
    expect(e).toBeInstanceOf(ApiError);
    expect([e.status, e.errorCode, e.message, e.requestId]).toEqual([409, "TRACE_SEQUENCE_CONFLICT", "m", "r-1"]);
  });

  it("falls back for FastAPI's default bodies and missing ids", () => {
    const e = fromBody(404, { detail: "Not Found" }, "client-id");
    expect([e.errorCode, e.message, e.requestId]).toEqual(["HTTP_404", "Not Found", "client-id"]);
  });
});
