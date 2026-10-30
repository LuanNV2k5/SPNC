import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { evidenceFields, signalSummary, tt } from "./vi";

// REQ-SIGNAL-004 / PROJECT_RULES #20-21: the system never judges the student (docs/47 D6)
const FORBIDDEN = ["gian lận", "không hiểu", "yếu", "có vấn đề", "đáng ngờ", "nghi ngờ", "cheat", "suspicious", "weak"];

describe("wording (docs/47 D6)", () => {
  it("no user-facing string contains a judgmental word", () => {
    const source = readFileSync(resolve(process.cwd(), "src/i18n/vi.ts"), "utf-8").toLowerCase();
    const strings = [...source.matchAll(/(["'`])((?:\.|(?!\1).)*)\1/g)].map((m) => m[2]!);
    for (const word of FORBIDDEN) {
      expect(strings.filter((s) => s.includes(word)), word).toEqual([]);
    }
  });

  it("every signal type has a label, a summary and evidence captions", () => {
    const samples: Record<string, Record<string, unknown>> = {
      IDLE_DETECTED: { duration_seconds: 600, threshold_used: 300 },
      FAST_FIRST_CODE: { delta_seconds: 4.2, threshold_seconds: 30 },
      REPEATED_FAILURE: { failed_count: 3 },
      LOC_ANOMALY: { observed_loc: 80, context_median_loc: 20, delta: 60 },
    };
    for (const [type, ev] of Object.entries(samples)) {
      expect(tt.signalType[type]).toBeTruthy();
      expect(evidenceFields[type]!.length).toBeGreaterThan(0);
      const text = signalSummary(type, ev).toLowerCase();
      FORBIDDEN.forEach((w) => expect(text).not.toContain(w));
    }
    expect(signalSummary("IDLE_DETECTED", samples.IDLE_DETECTED!)).toBe("Không có thao tác trong 10 phút (ngưỡng 5 phút)");
    expect(signalSummary("FAST_FIRST_CODE", samples.FAST_FIRST_CODE!)).toBe("Bắt đầu gõ code 4 giây sau khi mở đề (ngưỡng 30 giây)");
  });
});
