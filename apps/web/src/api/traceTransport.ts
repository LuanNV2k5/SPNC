import { TransportError, type TraceEvent, type TraceState, type TraceTransport } from "../trace";
import { api, call } from "./client";
import { toApiError } from "./errors";

const toTransport = (err: unknown): TransportError => {
  const e = toApiError(err);
  return new TransportError(e.status, e.errorCode, e.message, e.requestId);
};

/** The recorder's view of the ingest endpoints (docs/46 §3.5). */
export const traceTransport: TraceTransport = {
  async getState(sessionId: string): Promise<TraceState> {
    try {
      return await call(api.GET("/api/v1/my/coding-sessions/{session_id}/trace-state", { params: { path: { session_id: sessionId } } }));
    } catch (err) {
      throw toTransport(err);
    }
  },
  async sendBatch(sessionId: string, events: readonly TraceEvent[], opts?: { keepalive?: boolean }): Promise<TraceState> {
    try {
      const res = await call(
        api.POST("/api/v1/my/coding-sessions/{session_id}/trace-events/batch", {
          params: { path: { session_id: sessionId } },
          body: { events: events.map((e) => ({ ...e, payload: { ...e.payload } })) },
          keepalive: opts?.keepalive,
        }),
      );
      return res.state;
    } catch (err) {
      throw toTransport(err);
    }
  },
};
