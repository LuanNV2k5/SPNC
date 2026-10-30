import { TransportError, type TraceEvent, type TraceState, type TraceTransport } from "../trace";

/** Seeded PRNG so failure patterns are reproducible. */
export function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const canonical = (v: unknown): string =>
  v && typeof v === "object" && !Array.isArray(v)
    ? `{${Object.keys(v as object)
        .sort()
        .map((k) => `${JSON.stringify(k)}:${canonical((v as Record<string, unknown>)[k])}`)
        .join(",")}}`
    : JSON.stringify(v);

type Fault = "network" | "lost-response" | number;

const codeFor = (status: number) =>
  status === 403 ? "SESSION_NOT_ACTIVE" : status === 409 ? "TRACE_SEQUENCE_CONFLICT" : status === 401 ? "TOKEN_INVALID" : `HTTP_${status}`;

/**
 * In-memory model of the ingest endpoint (services/trace.py): idempotent on sequence number,
 * fingerprint over event_type + payload, 409 on conflicting content, 403 when not ACTIVE.
 */
export class FakeTraceServer implements TraceTransport {
  readonly events = new Map<number, TraceEvent & { fp: string }>();
  readonly requests: { at: number; sequences: number[]; keepalive: boolean }[] = [];
  active = true;
  offline = false;
  /** Faults consumed one per request before anything else. */
  faults: Fault[] = [];
  /** Random fault rate (network / lost response) when > 0. */
  faultRate = 0;
  random: () => number = mulberry32(1);
  checkpointInterval = 60;

  state(): TraceState {
    let h = 0;
    while (this.events.has(h + 1)) h++;
    return { highest_contiguous_sequence: h, next_expected_sequence: h + 1, checkpoint_interval_seconds: this.checkpointInterval };
  }

  async getState(): Promise<TraceState> {
    await Promise.resolve();
    if (this.offline) throw new TransportError(null, "NETWORK_ERROR", "offline", "r-state");
    return this.state();
  }

  async sendBatch(_sessionId: string, batch: readonly TraceEvent[], opts?: { keepalive?: boolean }): Promise<TraceState> {
    this.requests.push({ at: Date.now(), sequences: batch.map((e) => e.sequence_number), keepalive: !!opts?.keepalive });
    await Promise.resolve();
    if (this.offline) throw new TransportError(null, "NETWORK_ERROR", "offline", "r-off");
    let fault: Fault | undefined = this.faults.shift();
    if (fault === undefined && this.faultRate > 0 && this.random() < this.faultRate) {
      fault = this.random() < 0.5 ? "network" : "lost-response";
    }
    if (fault === "network") throw new TransportError(null, "NETWORK_ERROR", "fault", "r-net");
    if (typeof fault === "number") throw new TransportError(fault, codeFor(fault), "fault", "r-http");
    const fresh: (TraceEvent & { fp: string })[] = [];
    for (const e of batch) {
      const fp = `${e.event_type}:${canonical(e.payload)}`;
      const existing = this.events.get(e.sequence_number);
      if (existing && existing.fp !== fp) throw new TransportError(409, "TRACE_SEQUENCE_CONFLICT", `conflict at ${e.sequence_number}`, "r-409");
      if (!existing) fresh.push({ ...e, fp });
    }
    if (fresh.length && !this.active) throw new TransportError(403, "SESSION_NOT_ACTIVE", "inactive", "r-403");
    fresh.forEach((e) => this.events.set(e.sequence_number, e));
    if (fault === "lost-response") throw new TransportError(null, "NETWORK_ERROR", "response lost", "r-lost");
    return this.state();
  }

  sequences(): number[] {
    return [...this.events.keys()].sort((a, b) => a - b);
  }
}
