import { describe, expect, it } from "vitest";
import { participantDeadline } from "./deadline";

describe("participantDeadline", () => {
  it("uses the earlier of the participant duration and exam end", () => {
    expect(participantDeadline(
      { duration_minutes: 30, end_time: "2026-10-31T12:00:00Z" },
      { started_at: "2026-10-31T11:50:00Z" },
    )).toBe(Date.parse("2026-10-31T12:00:00Z"));
  });

  it("uses exam end when there is no per-participant duration", () => {
    expect(participantDeadline(
      { duration_minutes: null, end_time: "2026-10-31T12:00:00Z" },
      { started_at: "2026-10-31T11:00:00Z" },
    )).toBe(Date.parse("2026-10-31T12:00:00Z"));
  });

  it("does not derive a deadline until participation has started", () => {
    expect(participantDeadline(
      { duration_minutes: 30, end_time: "2026-10-31T12:00:00Z" },
      { started_at: null },
    )).toBeNull();
  });
});
