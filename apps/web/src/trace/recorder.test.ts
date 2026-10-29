import { describe, expect, it } from "vitest";
import { FakeTraceServer, mulberry32 } from "../test/fakeTraceServer";
import { FlushTimeoutError, RecorderStoppedError, TraceRecorder, openTraceStore, type RecorderOptions, type TraceStore } from ".";

let dbCounter = 0;
const newStore = () => openTraceStore(`trace-test-${++dbCounter}`);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i);

function open(store: TraceStore, server: FakeTraceServer, extra: Partial<RecorderOptions> = {}) {
  return TraceRecorder.open({
    sessionId: "s-1",
    userId: "u-1",
    problemId: "p-1",
    language: "PYTHON3",
    store,
    transport: server,
    flushDelayMs: 10,
    baseBackoffMs: 2,
    maxBackoffMs: 20,
    random: () => 1,
    ...extra,
  });
}

const edit = (i: number) => ({
  operation_type: "INSERT",
  range_offset: i,
  range_length: 0,
  text: "x",
  editor_version: String(i + 1),
  input_source: "typing",
});

describe("TraceRecorder", () => {
  it("sends events in order, contiguous from 1, in batches of at most maxBatch", async () => {
    const server = new FakeTraceServer();
    const r = await open(await newStore(), server, { maxBatch: 25, flushThreshold: 1000 });
    for (let i = 0; i < 120; i++) r.record("EDITOR_CHANGED", edit(i));
    expect(await r.flush()).toBe(120);
    expect(server.sequences()).toEqual(range(1, 120));
    for (const req of server.requests) {
      expect(req.sequences.length).toBeLessThanOrEqual(25);
      expect(req.sequences).toEqual(range(req.sequences[0]!, req.sequences[0]! + req.sequences.length - 1));
    }
    expect(server.requests.flatMap((q) => q.sequences)).toEqual(range(1, 120));
    r.dispose();
  });

  it("waits for the batch delay unless the threshold is reached", async () => {
    const server = new FakeTraceServer();
    const r = await open(await newStore(), server, { flushDelayMs: 60, flushThreshold: 5 });
    r.record("PROBLEM_OPENED", { problem_id: "p-1", language: "PYTHON3" });
    r.record("EDITOR_CHANGED", edit(0));
    await sleep(20);
    expect(server.requests).toHaveLength(0);
    await sleep(100);
    expect(server.requests).toHaveLength(1);
    for (let i = 1; i <= 5; i++) r.record("EDITOR_CHANGED", edit(i));
    await sleep(20);
    expect(server.requests).toHaveLength(2);
    expect(server.sequences()).toEqual(range(1, 7));
    r.dispose();
  });

  it("loses nothing and duplicates nothing under random network faults and lost responses", async () => {
    const server = new FakeTraceServer();
    server.faultRate = 0.35;
    server.random = mulberry32(42);
    const r = await open(await newStore(), server, { maxBatch: 17, flushThreshold: 10 });
    const rnd = mulberry32(7);
    for (let i = 0; i < 300; i++) {
      r.record("EDITOR_CHANGED", edit(i));
      if (rnd() < 0.1) await sleep(1);
    }
    expect(await r.flush(10_000)).toBe(300);
    expect(server.sequences()).toEqual(range(1, 300));
    server.sequences().forEach((s) => expect(server.events.get(s)!.payload).toEqual(edit(s - 1)));
    expect(server.requests.length).toBeGreaterThan(300 / 17);
    r.dispose();
  });

  it("retries with growing backoff and succeeds", async () => {
    const server = new FakeTraceServer();
    server.faults = ["network", 503, 429];
    const r = await open(await newStore(), server, { baseBackoffMs: 10, maxBackoffMs: 1000 });
    r.record("EDITOR_CHANGED", edit(0));
    expect(await r.flush()).toBe(1);
    const t = server.requests.map((q) => q.at);
    expect(t).toHaveLength(4);
    const gaps = t.slice(1).map((v, i) => v - t[i]!);
    expect(gaps[0]).toBeGreaterThanOrEqual(9);
    expect(gaps[1]).toBeGreaterThanOrEqual(19);
    expect(gaps[2]).toBeGreaterThanOrEqual(39);
    r.dispose();
  });

  it("recovers after a reload: unsent events are resent and numbering continues", async () => {
    const store = await newStore();
    const server = new FakeTraceServer();
    server.offline = true;
    const a = await open(store, server);
    for (let i = 0; i < 30; i++) a.record("EDITOR_CHANGED", edit(i));
    await expect(a.flush(50)).rejects.toBeInstanceOf(FlushTimeoutError);
    a.dispose(); // the page is gone

    server.offline = false;
    const b = await open(store, server);
    expect(b.lastSequence).toBe(30);
    for (let i = 30; i < 40; i++) b.record("EDITOR_CHANGED", edit(i));
    expect(await b.flush()).toBe(40);
    expect(server.sequences()).toEqual(range(1, 40));
    expect(await store.pending("s-1")).toHaveLength(0);
    b.dispose();
  });

  it("a resend after a lost response is accepted as an identical duplicate", async () => {
    const store = await newStore();
    const server = new FakeTraceServer();
    server.faults = ["lost-response"];
    const a = await open(store, server, { baseBackoffMs: 10_000, maxBackoffMs: 10_000 });
    for (let i = 0; i < 5; i++) a.record("EDITOR_CHANGED", edit(i));
    await sleep(40); // stored on the server, response lost, now waiting in backoff
    expect(server.sequences()).toEqual(range(1, 5));
    a.dispose();
    const b = await open(store, server);
    expect(await b.flush()).toBe(5);
    expect(server.sequences()).toEqual(range(1, 5));
    b.dispose();
  });

  it("keeps numbering monotonic when reopened offline with an empty queue", async () => {
    const store = await newStore();
    const server = new FakeTraceServer();
    const a = await open(store, server);
    for (let i = 0; i < 5; i++) a.record("EDITOR_CHANGED", edit(i));
    await a.flush();
    a.dispose();
    server.offline = true;
    const b = await open(store, server);
    expect(b.record("EDITOR_CHANGED", edit(5))).toBe(6);
    server.offline = false;
    b.kick();
    expect(await b.flush()).toBe(6);
    expect(server.sequences()).toEqual(range(1, 6));
    b.dispose();
  });

  it("flush barrier resolves only after acknowledgement", async () => {
    const server = new FakeTraceServer();
    server.offline = true;
    const r = await open(await newStore(), server);
    r.record("EDITOR_CHANGED", edit(0));
    r.record("EDITOR_CHANGED", edit(1));
    await expect(r.flush(30)).rejects.toBeInstanceOf(FlushTimeoutError);
    expect(server.events.size).toBe(0);
    server.offline = false;
    expect(await r.flush()).toBe(2);
    expect(r.status.pending).toBe(0);
    r.dispose();
  });

  it("403 closes the recorder and keeps the unsent events", async () => {
    const store = await newStore();
    const server = new FakeTraceServer();
    server.active = false;
    const r = await open(store, server);
    r.record("EDITOR_CHANGED", edit(0));
    const err = (await r.flush().catch((e: unknown) => e)) as RecorderStoppedError;
    expect(err).toBeInstanceOf(RecorderStoppedError);
    expect(err.phase).toBe("closed");
    expect(r.status.error?.errorCode).toBe("SESSION_NOT_ACTIVE");
    expect(r.record("EDITOR_CHANGED", edit(1))).toBeNull();
    expect((await store.pending("s-1")).map((e) => e.sequence_number)).toEqual([1]);
    r.dispose();
  });

  it("409 stops sending without dropping events", async () => {
    const store = await newStore();
    const server = new FakeTraceServer();
    server.faults = [409];
    const r = await open(store, server);
    r.record("EDITOR_CHANGED", edit(0));
    const err = (await r.flush().catch((e: unknown) => e)) as RecorderStoppedError;
    expect(err.phase).toBe("failed");
    expect(err.cause?.errorCode).toBe("TRACE_SEQUENCE_CONFLICT");
    expect(await store.pending("s-1")).toHaveLength(1);
    r.dispose();
  });

  it("401 pauses until resume()", async () => {
    const server = new FakeTraceServer();
    server.faults = [401];
    const r = await open(await newStore(), server);
    r.record("EDITOR_CHANGED", edit(0));
    await sleep(40);
    expect(r.status.phase).toBe("auth");
    expect(r.record("EDITOR_CHANGED", edit(1))).toBe(2); // still recorded locally
    r.resume();
    expect(await r.flush()).toBe(2);
    expect(server.sequences()).toEqual([1, 2]);
    r.dispose();
  });

  it("finish() forgets the session locally once flushed", async () => {
    const store = await newStore();
    const server = new FakeTraceServer();
    const r = await open(store, server);
    r.record("EDITOR_CHANGED", edit(0));
    await r.flush();
    await store.putDraft({ session_id: "s-1", user_id: "u-1", content: "x", updated_at: "now" });
    await r.finish();
    expect(await store.getMeta("s-1")).toBeUndefined();
    expect(await store.getDraft("s-1")).toBeUndefined();
    expect(r.record("EDITOR_CHANGED", edit(1))).toBeNull();
  });

  it("payloads are frozen: mutating the caller's object does not change the sent event", async () => {
    const server = new FakeTraceServer();
    const r = await open(await newStore(), server);
    const p = { ...edit(0) };
    r.record("EDITOR_CHANGED", p);
    p.text = "changed";
    await r.flush();
    expect(server.events.get(1)!.payload).toEqual(edit(0));
    r.dispose();
  });

  it("beacon sends persisted events with keepalive", async () => {
    const server = new FakeTraceServer();
    const r = await open(await newStore(), server, { flushDelayMs: 10_000 });
    r.record("EDITOR_CHANGED", edit(0));
    await sleep(10);
    r.beacon();
    await sleep(10);
    expect(server.requests.some((q) => q.keepalive)).toBe(true);
    r.dispose();
  });
});
