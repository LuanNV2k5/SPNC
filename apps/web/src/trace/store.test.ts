import { describe, expect, it } from "vitest";
import { openTraceStore } from ".";

describe("TraceStore", () => {
  it("clears all data of one user and counts pending events", async () => {
    const s = await openTraceStore("store-test-1");
    for (const [sid, uid] of [
      ["a", "u1"],
      ["b", "u1"],
      ["c", "u2"],
    ] as const) {
      await s.putMeta({ session_id: sid, user_id: uid, problem_id: "p", language: "CPP17", acked_through: 0 });
      await s.putEvent({ session_id: sid, sequence_number: 1, event_type: "PROBLEM_OPENED", client_timestamp: "t", payload: {} });
      await s.putDraft({ session_id: sid, user_id: uid, content: "c", updated_at: "t" });
    }
    expect(await s.pendingCountOf("u1")).toBe(2);
    await s.clearUser("u1");
    expect(await s.pendingCountOf("u1")).toBe(0);
    expect(await s.getDraft("a")).toBeUndefined();
    expect(await s.getDraft("c")).toBeDefined();
    expect(await s.pending("c")).toHaveLength(1);
  });

  it("ack deletes up to the sequence and advances acked_through", async () => {
    const s = await openTraceStore("store-test-2");
    await s.putMeta({ session_id: "a", user_id: "u", problem_id: "p", language: "CPP17", acked_through: 0 });
    for (let i = 1; i <= 5; i++) {
      await s.putEvent({ session_id: "a", sequence_number: i, event_type: "EDITOR_CHANGED", client_timestamp: "t", payload: {} });
    }
    await s.ack("a", 3);
    expect((await s.pending("a")).map((e) => e.sequence_number)).toEqual([4, 5]);
    expect((await s.getMeta("a"))!.acked_through).toBe(3);
    expect(await s.maxEventSequence("a")).toBe(5);
  });
});
