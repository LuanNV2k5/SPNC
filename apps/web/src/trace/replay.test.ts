import { describe, expect, it } from "vitest";
import { mulberry32 } from "../test/fakeTraceServer";
import { editorChangedPayloads } from "./payloads";
import { Replay, type ReplayEvent } from "./replay";

let seq = 0;
const ev = (event_type: string, payload: Record<string, unknown> = {}): ReplayEvent => ({ sequence_number: ++seq, event_type, payload });
const typed = (offset: number, text: string, version = 1) =>
  editorChangedPayloads([{ rangeOffset: offset, rangeLength: 0, text }], version, "typing").map((p) => ev("EDITOR_CHANGED", p));

describe("Replay (docs/47 D3)", () => {
  it("rebuilds the code event by event", () => {
    seq = 0;
    const events = [ev("PROBLEM_OPENED"), ...typed(0, "ab"), ...typed(2, "c"), ...editorChangedPayloads([{ rangeOffset: 0, rangeLength: 1, text: "" }], 3, "typing").map((p) => ev("EDITOR_CHANGED", p))];
    const r = new Replay(events);
    expect([0, 1, 2, 3, 4].map((s) => r.codeAt(s))).toEqual(["", "", "ab", "abc", "bc"]);
    expect(r.gapAfter).toBeNull();
  });

  it("stops at a gap and at the server's contiguous limit", () => {
    seq = 0;
    const events = [ev("PROBLEM_OPENED"), ...typed(0, "a")];
    seq = 5;
    events.push(...typed(1, "b"));
    const r = new Replay(events);
    expect(r.lastSequence).toBe(2);
    expect(r.gapAfter).toBe(2);
    expect(r.codeAt(99)).toBe("a");
    const limited = new Replay(events.slice(0, 2), { highestContiguous: 1 });
    expect(limited.lastSequence).toBe(1);
    expect(limited.gapAfter).toBe(1);
  });

  it("memoised seeking gives the same code as a full replay", () => {
    seq = 0;
    const rnd = mulberry32(3);
    const events: ReplayEvent[] = [ev("PROBLEM_OPENED")];
    let doc = "";
    for (let i = 0; i < 3000; i++) {
      const off = Math.floor(rnd() * (doc.length + 1));
      const del = rnd() < 0.3 ? Math.min(doc.length - off, Math.floor(rnd() * 3)) : 0;
      const text = rnd() < 0.8 ? String.fromCharCode(97 + Math.floor(rnd() * 26)) : "";
      const ps = editorChangedPayloads([{ rangeOffset: off, rangeLength: del, text }], i, "typing");
      ps.forEach((p) => events.push(ev("EDITOR_CHANGED", p)));
      if (ps.length) doc = doc.slice(0, off) + text + doc.slice(off + del);
    }
    const fast = new Replay(events, { memoEvery: 100 });
    const slow = new Replay(events, { memoEvery: 1_000_000 });
    for (const s of [fast.lastSequence, 1500, 7, 2999, 1500, 0]) expect(fast.codeAt(s)).toBe(slow.codeAt(s));
    expect(fast.codeAt(fast.lastSequence)).toBe(doc);
  });

  it("verifies snapshots, tolerating keystrokes between snapshot and its event", () => {
    seq = 0;
    const events = [ev("PROBLEM_OPENED"), ...typed(0, "ab"), ...typed(2, "c"), ev("RUN_REQUESTED", { code_snapshot_id: "s1" })];
    const r = new Replay(events);
    const [p] = r.snapshotPoints();
    expect(p).toEqual({ sequence: 4, snapshotId: "s1", eventType: "RUN_REQUESTED" });
    expect(r.verify(p!, "ab")).toEqual({ status: "match", sequence: 4, matchedAt: 2 });
    expect(r.codeAt(4)).toBe("abc"); // a match never changes the replay
  });

  it("rebases on a mismatch so later diffs apply to the snapshot content", () => {
    seq = 0;
    // The first keystroke is missing from the trace (e.g. a session resumed without its draft)
    const events = [ev("PROBLEM_OPENED"), ev("SESSION_CHECKPOINT", { code_snapshot_id: "s1" }), ...typed(2, "Z")];
    const r = new Replay(events);
    expect(r.codeAt(3)).toBe("Z");
    const v = r.verify(r.snapshotPoints()[0]!, "xy");
    expect(v.status).toBe("mismatch");
    expect(r.codeAt(2)).toBe("xy");
    expect(r.codeAt(3)).toBe("xyZ");
    expect(r.verification("s1")).toEqual(v);
  });

  it("seeks in a 20 000-event session in under a second", () => {
    seq = 0;
    const events: ReplayEvent[] = [ev("PROBLEM_OPENED")];
    for (let i = 0; i < 20_000; i++) events.push(...typed(i, "x", i));
    const r = new Replay(events);
    const t0 = performance.now();
    r.codeAt(r.lastSequence);
    for (let s = 0; s < 50; s++) r.codeAt(Math.floor((s / 50) * r.lastSequence));
    expect(performance.now() - t0).toBeLessThan(1000);
    expect(r.codeAt(r.lastSequence).length).toBe(20_000);
  });
});
