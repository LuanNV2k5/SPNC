import { applyEditorChanges, type EditorChangedPayload } from "./payloads";

/** One stored trace event as the teacher API returns it (docs/47 §3.3). */
export interface ReplayEvent {
  sequence_number: number;
  event_type: string;
  payload: Record<string, unknown>;
  server_timestamp?: string;
  client_timestamp?: string;
}

export interface SnapshotPoint {
  sequence: number;
  snapshotId: string;
  eventType: string;
}

export type Verification =
  | { status: "match"; sequence: number; matchedAt: number }
  | { status: "mismatch"; sequence: number };

export interface ReplayOptions {
  /** Server's highest contiguous sequence; the replay never goes beyond it. */
  highestContiguous?: number;
  /** Memoise the code every this many events (fast seek in long sessions). */
  memoEvery?: number;
  /**
   * A snapshot taken just before its event (the client creates the snapshot, then records the
   * event) may miss up to this many later keystrokes; it is matched against the code at any of the
   * preceding events within this window.
   */
  matchWindow?: number;
}

const SNAPSHOT_EVENTS = new Set(["SESSION_CHECKPOINT", "RUN_REQUESTED", "SUBMISSION_CREATED"]);

/**
 * Rebuilds the code of a session from its EDITOR_CHANGED diffs (docs/47 D3).
 * - Only the contiguous prefix from sequence 1 is replayed; `gapAfter` says where it stops.
 * - Snapshots verify the replay; after a mismatch the replay continues from the snapshot content.
 */
export class Replay {
  readonly events: ReplayEvent[];
  /** Last replayable sequence when a gap or the server's contiguous limit stops the replay. */
  readonly gapAfter: number | null;
  private readonly memoEvery: number;
  private readonly matchWindow: number;
  /** code after event index i, for indexes that are multiples of memoEvery or rebased */
  private memo = new Map<number, string>();
  private overrides = new Map<number, string>();
  private readonly verified = new Map<string, Verification>();

  constructor(all: readonly ReplayEvent[], opts: ReplayOptions = {}) {
    this.memoEvery = opts.memoEvery ?? 500;
    this.matchWindow = opts.matchWindow ?? 50;
    const sorted = [...all].sort((a, b) => a.sequence_number - b.sequence_number);
    const limit = opts.highestContiguous ?? Number.MAX_SAFE_INTEGER;
    const events: ReplayEvent[] = [];
    let gap: number | null = null;
    for (const e of sorted) {
      const expected = events.length + 1;
      if (e.sequence_number !== expected || e.sequence_number > limit) {
        gap = expected - 1;
        break;
      }
      events.push(e);
    }
    this.events = events;
    this.gapAfter = gap;
  }

  get lastSequence(): number {
    return this.events.length;
  }

  /** Events carrying a snapshot id, in order. */
  snapshotPoints(): SnapshotPoint[] {
    return this.events.flatMap((e) => {
      const id = e.payload.code_snapshot_id;
      return SNAPSHOT_EVENTS.has(e.event_type) && typeof id === "string" ? [{ sequence: e.sequence_number, snapshotId: id, eventType: e.event_type }] : [];
    });
  }

  /** Code after the event with this sequence (0 = before any event). */
  codeAt(sequence: number): string {
    const target = Math.max(0, Math.min(sequence, this.events.length));
    let start = 0;
    let code = "";
    for (const [idx, c] of this.memo) {
      if (idx <= target && idx > start) {
        start = idx;
        code = c;
      }
    }
    for (const [idx, c] of this.overrides) {
      if (idx <= target && idx >= start) {
        start = idx;
        code = c;
      }
    }
    for (let i = start + 1; i <= target; i++) {
      const e = this.events[i - 1]!;
      if (e.event_type === "EDITOR_CHANGED") code = applyEditorChanges(code, [e.payload as unknown as EditorChangedPayload]);
      if (this.overrides.has(i)) code = this.overrides.get(i)!;
      if (i % this.memoEvery === 0) this.memo.set(i, code);
    }
    return code;
  }

  /**
   * Checks the replay against a snapshot's content. Call in increasing sequence order.
   * On a mismatch the snapshot content becomes the code at that point (rebase).
   */
  verify(point: SnapshotPoint, content: string): Verification {
    const known = this.verified.get(point.snapshotId);
    if (known) return known;
    let result: Verification = { status: "mismatch", sequence: point.sequence };
    for (let s = point.sequence; s >= Math.max(0, point.sequence - this.matchWindow); s--) {
      if (this.codeAt(s) === content) {
        result = { status: "match", sequence: point.sequence, matchedAt: s };
        break;
      }
    }
    if (result.status === "mismatch") {
      this.overrides.set(point.sequence, content);
      for (const idx of [...this.memo.keys()]) if (idx >= point.sequence) this.memo.delete(idx);
    }
    this.verified.set(point.snapshotId, result);
    return result;
  }

  verification(snapshotId: string): Verification | undefined {
    return this.verified.get(snapshotId);
  }
}
