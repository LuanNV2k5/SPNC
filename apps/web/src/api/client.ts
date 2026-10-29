import createClient from "openapi-fetch";
import { TIMEOUT_MS, getAccessToken, refreshAccessToken } from "./auth";
import { ApiError, fromBody, newRequestId } from "./errors";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

function prepare(req: Request, requestId: string): Request {
  const headers = new Headers(req.headers);
  headers.set("X-Request-ID", requestId);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else headers.delete("Authorization");
  return new Request(req, { headers, signal: AbortSignal.timeout(TIMEOUT_MS) });
}

async function send(req: Request, requestId: string): Promise<Response> {
  try {
    return await fetch(prepare(req, requestId));
  } catch (err) {
    throw new ApiError(null, "NETWORK_ERROR", err instanceof Error ? err.message : String(err), requestId);
  }
}

/**
 * Every REST call: a fresh X-Request-ID (docs/46 §3.2) and, on 401, one token refresh followed
 * by one retry of the original request (§3.3).
 */
async function authFetch(input: Request): Promise<Response> {
  const retry = input.clone();
  const first = await send(input, newRequestId());
  if (first.status !== 401) return first;
  if (!(await refreshAccessToken())) return first;
  return send(retry, newRequestId());
}

export const api = createClient<paths>({ baseUrl: "", fetch: authFetch });

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Returns the data of a call or throws an ApiError carrying error_code and request_id. */
export async function call<T>(p: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await p;
  if (response.ok) return data as T;
  throw fromBody(response.status, error, response.headers.get("X-Request-ID") ?? "");
}
