/** Uniform error shape shown to the user (PROJECT_RULES #29, docs/46 §3.4). */
export class ApiError extends Error {
  constructor(
    readonly status: number | null,
    readonly errorCode: string,
    message: string,
    readonly requestId: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const newRequestId = (): string => crypto.randomUUID();

/** Builds an ApiError from a backend error body `{error_code, message, request_id, details?}`. */
export function fromBody(status: number, body: unknown, fallbackRequestId: string): ApiError {
  const b = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  // FastAPI's default 404/405 bodies carry `detail` instead of the project shape
  const message = typeof b.message === "string" ? b.message : typeof b.detail === "string" ? b.detail : `HTTP ${status}`;
  return new ApiError(
    status,
    typeof b.error_code === "string" ? b.error_code : `HTTP_${status}`,
    message,
    typeof b.request_id === "string" && b.request_id ? b.request_id : fallbackRequestId,
    b.details,
  );
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  const message = err instanceof Error ? err.message : String(err);
  return new ApiError(null, "NETWORK_ERROR", message, "");
}
