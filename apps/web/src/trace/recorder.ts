import { backoffDelay } from "./backoff";
import type { TraceStore } from "./store";
import {
  TransportError,
  type ClientEventType,
  type RecorderPhase,
  type RecorderStatus,
  type StoredEvent,
  type TraceEvent,
  type TraceState,
  type TraceTransport,
} from "./types";

export interface RecorderOptions {
  sessionId: string;
  userId: string;
  problemId: string;
  language: string;
  store: TraceStore;
  transport: TraceTransport;
  onStatus?: (s: RecorderStatus) => void;
  now?: () => Date;
  random?: () => number;
  /** Events per request (server limit 1000). */
  maxBatch?: number;
  /** Send at once when this many persisted events wait. */
  flushThreshold?: number;
  /** Otherwise send this long after the first unsent event. */
  flushDelayMs?: number;
  baseBackoffMs?: number;
  maxBackoffMs?: number;
}

/** flush() could not empty the queue in time; recording and retries continue. */
export class FlushTimeoutError extends Error {
  constructor() {
    super("Trace queue not flushed in time");
    this.name = "FlushTimeoutError";
  }
}

/** The recorder stopped sending (closed, failed or auth) while events were still unsent. */
export class RecorderStoppedError extends Error {
  constructor(
    readonly phase: RecorderPhase,
    readonly cause?: TransportError,
  ) {
    super(`Trace recorder stopped: ${phase}`);
    this.name = "RecorderStoppedError";
  }
}

type Outcome = "retry" | "auth" | "closed" | "failed";

function classify(e: TransportError): Outcome {
  if (e.status === null || e.status === 408 || e.status === 429 || e.status >= 500) return "retry";
  if (e.status === 401) return "auth";
  if (e.status === 403) return "closed";
  return "failed";
}

function toTransportError(err: unknown): TransportError {
  if (err instanceof TransportError) return err;
  return new TransportError(null, "NETWORK_ERROR", err instanceof Error ? err.message : String(err), "");
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

const strip = ({ sequence_number, event_type, client_timestamp, payload }: StoredEvent): TraceEvent => ({
  sequence_number,
  event_type,
  client_timestamp,
  payload,
});

interface Waiter {
  resolve: (lastAcked: number) => void;
  reject: (e: Error) => void;
}

/**
 * Records the trace of one coding session (docs/46 §3.5).
 * Sequence numbers are allocated here, every event is persisted before it may be sent,
 * and it is deleted only after the server acknowledged it.
 */
export class TraceRecorder {
  private readonly o: Required<Omit<RecorderOptions, "onStatus">> & Pick<RecorderOptions, "onStatus">;
  private next = 1;
  private queue: StoredEvent[] = [];
  private persistedThrough = 0;
  private lastAcked = 0;
  private writes: Promise<void> = Promise.resolve();
  private phase: RecorderPhase = "idle";
  private error: TransportError | undefined;
  private inflight: Promise<void> | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private backoffTimer: ReturnType<typeof setTimeout> | null = null;
  private wake: (() => void) | null = null;
  private attempt = 0;
  private waiters: Waiter[] = [];
  private disposed = false;
  private checkpointSeconds = 60;

  private constructor(opts: RecorderOptions) {
    this.o = {
      now: () => new Date(),
      random: Math.random,
      maxBatch: 200,
      flushThreshold: 50,
      flushDelayMs: 2000,
      baseBackoffMs: 1000,
      maxBackoffMs: 30_000,
      ...opts,
    };
  }

  /** Opens the recorder: resumes persisted events and continues the numbering (rule 1). */
  static async open(opts: RecorderOptions): Promise<TraceRecorder> {
    const r = new TraceRecorder(opts);
    await r.init();
    return r;
  }

  private async init(): Promise<void> {
    const { store, transport, sessionId } = this.o;
    let meta = await store.getMeta(sessionId);
    if (!meta) {
      meta = { session_id: sessionId, user_id: this.o.userId, problem_id: this.o.problemId, language: this.o.language, acked_through: 0 };
      await store.putMeta(meta);
    }
    const local = await store.pending(sessionId);
    const localMax = local.length ? local[local.length - 1]!.sequence_number : 0;
    let server: TraceState | null = null;
    try {
      server = await transport.getState(sessionId);
    } catch (err) {
      // Offline: continue from local knowledge. Any other error (403, 404) is the caller's to show.
      if (classify(toTransportError(err)) !== "retry") throw err;
    }
    if (server?.checkpoint_interval_seconds) this.checkpointSeconds = server.checkpoint_interval_seconds;
    this.next = Math.max(server?.next_expected_sequence ?? 1, localMax + 1, meta.acked_through + 1);
    // Events are deleted only once acknowledged, so everything below the first pending one is
    this.lastAcked = local.length
      ? local[0]!.sequence_number - 1
      : Math.max(meta.acked_through, server?.highest_contiguous_sequence ?? 0);
    this.queue = local;
    this.persistedThrough = localMax;
    this.emit();
    if (local.length) void this.pump();
  }

  get checkpointIntervalSeconds(): number {
    return this.checkpointSeconds;
  }

  /** Highest sequence number allocated so far (for `last_sequence_number` on end). */
  get lastSequence(): number {
    return this.next - 1;
  }

  get status(): RecorderStatus {
    return { phase: this.phase, pending: this.queue.length, lastAcked: this.lastAcked, error: this.error };
  }

  get stopped(): boolean {
    return this.phase === "closed" || this.phase === "failed" || this.phase === "auth";
  }

  /** Appends one event. Returns its sequence number, or null when the recorder no longer records. */
  record(eventType: ClientEventType, payload: Record<string, unknown> = {}): number | null {
    if (this.disposed || this.phase === "closed" || this.phase === "failed") return null;
    const event: StoredEvent = deepFreeze({
      session_id: this.o.sessionId,
      sequence_number: this.next++,
      event_type: eventType,
      client_timestamp: this.o.now().toISOString(),
      payload: structuredClone(payload),
    });
    this.queue.push(event);
    this.writes = this.writes.then(async () => {
      try {
        await this.o.store.putEvent(event);
        this.persistedThrough = event.sequence_number;
        this.schedule();
      } catch (err) {
        this.stop("failed", new TransportError(null, "TRACE_STORE_ERROR", err instanceof Error ? err.message : String(err), ""));
      }
    });
    this.emit();
    return event.sequence_number;
  }

  /** Retries now instead of waiting for the backoff (e.g. the browser came back online). */
  kick(): void {
    if (this.wake) this.wake();
    else this.schedule(true);
  }

  /** After re-login: continue sending after a 401. */
  resume(): void {
    if (this.phase !== "auth") return;
    this.phase = "idle";
    this.error = undefined;
    this.emit();
    void this.pump();
  }

  /**
   * Flush barrier (rule 9): resolves with the last acknowledged sequence once every event
   * recorded so far is acknowledged. Rejects on timeout or when sending stopped.
   */
  async flush(timeoutMs = 15_000): Promise<number> {
    await this.writes;
    if (!this.queue.length) return this.lastAcked;
    if (this.stopped) throw new RecorderStoppedError(this.phase, this.error);
    return new Promise<number>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiters = this.waiters.filter((w) => w !== waiter);
        reject(new FlushTimeoutError());
      }, timeoutMs);
      const waiter: Waiter = {
        resolve: (n) => {
          clearTimeout(timer);
          resolve(n);
        },
        reject: (e) => {
          clearTimeout(timer);
          reject(e);
        },
      };
      this.waiters.push(waiter);
      this.kick();
    });
  }

  /** Best effort on page close (rule 8): one keepalive request, result ignored. */
  beacon(): void {
    const batch = this.readyBatch();
    if (batch.length && !this.stopped) {
      this.o.transport.sendBatch(this.o.sessionId, batch.map(strip), { keepalive: true }).catch(() => {});
    }
  }

  /** The session ended on the server (submit or end) and the queue is empty: forget it locally. */
  async finish(): Promise<void> {
    await this.writes;
    this.stop("closed");
    if (!this.queue.length) await this.o.store.deleteSession(this.o.sessionId);
  }

  /** Stops timers (component unmount). Persisted events stay for the next open. */
  dispose(): void {
    this.disposed = true;
    this.clearTimers();
  }

  private readyBatch(): StoredEvent[] {
    const out: StoredEvent[] = [];
    for (const e of this.queue) {
      if (e.sequence_number > this.persistedThrough || out.length >= this.o.maxBatch) break;
      out.push(e);
    }
    return out;
  }

  private schedule(now = false): void {
    if (this.disposed || this.stopped || this.inflight || this.backoffTimer) return;
    const ready = this.readyBatch().length;
    if (!ready) return;
    if (now || ready >= this.o.flushThreshold || this.waiters.length) {
      void this.pump();
    } else if (!this.flushTimer) {
      this.flushTimer = setTimeout(() => {
        this.flushTimer = null;
        void this.pump();
      }, this.o.flushDelayMs);
    }
  }

  private pump(): Promise<void> {
    if (!this.inflight) {
      this.inflight = this.run().finally(() => {
        this.inflight = null;
        this.schedule();
      });
    }
    return this.inflight;
  }

  private async run(): Promise<void> {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    while (!this.disposed && !this.stopped) {
      const batch = this.readyBatch();
      if (!batch.length) {
        this.setPhase("idle");
        this.settleWaiters();
        return;
      }
      this.setPhase("sending");
      try {
        const state = await this.o.transport.sendBatch(this.o.sessionId, batch.map(strip));
        this.attempt = 0;
        this.error = undefined;
        const first = batch[0]!.sequence_number;
        const through = Math.min(batch[batch.length - 1]!.sequence_number, state.highest_contiguous_sequence);
        if (through < first) {
          // The server lacks events before this batch: never expected, so stop instead of looping
          this.stop("failed", new TransportError(200, "TRACE_GAP", `Server acknowledged up to ${state.highest_contiguous_sequence}, batch starts at ${first}`, ""));
          return;
        }
        await this.o.store.ack(this.o.sessionId, through);
        this.queue = this.queue.filter((e) => e.sequence_number > through);
        this.lastAcked = Math.max(this.lastAcked, through);
        this.emit();
      } catch (err) {
        const te = toTransportError(err);
        const outcome = classify(te);
        if (outcome !== "retry") {
          this.stop(outcome, te);
          return;
        }
        this.error = te;
        this.setPhase("retrying");
        await this.sleep(backoffDelay(this.attempt++, this.o.baseBackoffMs, this.o.maxBackoffMs, this.o.random));
      }
    }
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const done = () => {
        if (this.backoffTimer) clearTimeout(this.backoffTimer);
        this.backoffTimer = null;
        this.wake = null;
        resolve();
      };
      this.wake = done;
      this.backoffTimer = setTimeout(done, ms);
    });
  }

  private stop(phase: "closed" | "failed" | "auth", error?: TransportError): void {
    this.phase = phase;
    this.error = error;
    this.clearTimers();
    const pending = this.queue.length;
    const waiters = this.waiters;
    this.waiters = [];
    waiters.forEach((w) => (pending ? w.reject(new RecorderStoppedError(phase, error)) : w.resolve(this.lastAcked)));
    this.emit();
  }

  private settleWaiters(): void {
    if (this.queue.length) return;
    const waiters = this.waiters;
    this.waiters = [];
    waiters.forEach((w) => w.resolve(this.lastAcked));
  }

  private clearTimers(): void {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = null;
    if (this.wake) this.wake();
  }

  private setPhase(p: RecorderPhase): void {
    if (this.phase !== p) {
      this.phase = p;
      this.emit();
    }
  }

  private emit(): void {
    this.o.onStatus?.(this.status);
  }
}
