import { describe, expect, it } from "vitest";
import { applyEditorChanges, backoffDelay, editorChangedPayloads, lineCount, operationType } from ".";

describe("payloads", () => {
  it("maps changes to the domain operation types", () => {
    expect(operationType({ rangeOffset: 0, rangeLength: 0, text: "a" })).toBe("INSERT");
    expect(operationType({ rangeOffset: 0, rangeLength: 2, text: "" })).toBe("DELETE");
    expect(operationType({ rangeOffset: 0, rangeLength: 2, text: "b" })).toBe("REPLACE");
    expect(operationType({ rangeOffset: 0, rangeLength: 0, text: "" })).toBeNull();
  });

  it("multi-cursor edits replay to the edited content and carry diffs only", () => {
    const before = "abc\nabc\nabc";
    const changes = [
      { rangeOffset: 0, rangeLength: 1, text: "X" },
      { rangeOffset: 8, rangeLength: 0, text: "YY" },
      { rangeOffset: 4, rangeLength: 3, text: "" },
    ];
    const payloads = editorChangedPayloads(changes, 7, "typing");
    expect(payloads.map((p) => p.range_offset)).toEqual([8, 4, 0]);
    expect(payloads.map((p) => p.operation_type)).toEqual(["INSERT", "DELETE", "REPLACE"]);
    expect(applyEditorChanges(before, payloads)).toBe("Xbc\n\nYYabc");
    payloads.forEach((p) => {
      expect(p.editor_version).toBe("7");
      expect(Object.keys(p).sort()).toEqual(["editor_version", "input_source", "operation_type", "range_length", "range_offset", "text"]);
    });
  });

  it("counts lines", () => {
    expect(lineCount("")).toBe(0);
    expect(lineCount("a")).toBe(1);
    expect(lineCount("a\nb\n")).toBe(3);
  });

  it("backoff doubles up to the cap", () => {
    const one = () => 1;
    expect([0, 1, 2, 3, 10].map((a) => backoffDelay(a, 1000, 30_000, one))).toEqual([1000, 2000, 4000, 8000, 30_000]);
    expect(backoffDelay(0, 1000, 30_000, () => 0)).toBe(500);
  });
});
