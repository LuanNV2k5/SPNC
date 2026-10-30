/** Client side of the trace contract (docs/46 §3.5, D9; server: app/api/endpoints/trace.py). */

/** Event types a client may send. SESSION_ENDED and SUBMISSION_CREATED are server-only (F7). */
export type ClientEventType =
  | "PROBLEM_OPENED"
  | "EDITOR_CHANGED"
  | "SNAPSHOT_CREATED"
  | "RUN_REQUESTED"
  | "RUN_COMPLETED"
  | "SESSION_CHECKPOINT";

export type Payload = Readonly<Record<string, unknown>>;

/** One event as sent in a batch. Frozen at creation so a resend is identical (F6). */
export interface TraceEvent {
  readonly sequence_number: number;
  readonly event_type: ClientEventType;
  readonly client_timestamp: string;
  readonly payload: Payload;
}

export interface StoredEvent extends TraceEvent {
  readonly session_id: string;
}

export interface TraceState {
  highest_contiguous_sequence: number;
  next_expected_sequence: number;
  checkpoint_interval_seconds?: number;
}

/** Failure of one transport call. `status` is null for network errors and timeouts. */
export class TransportError extends Error {
  constructor(
    readonly status: number | null,
    readonly errorCode: string,
    message: string,
    readonly requestId: string,
  ) {
    super(message);
    this.name = "TransportError";
  }
}

export interface TraceTransport {
  getState(sessionId: string): Promise<TraceState>;
  sendBatch(sessionId: string, events: readonly TraceEvent[], opts?: { keepalive?: boolean }): Promise<TraceState>;
}

/** idle: nothing to send; retrying: waiting for backoff; the last three stop sending. */
export type RecorderPhase = "idle" | "sending" | "retrying" | "closed" | "failed" | "auth";

export interface RecorderStatus {
  phase: RecorderPhase;
  pending: number;
  lastAcked: number;
  error?: TransportError;
}
