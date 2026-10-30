/**
 * Payload builders for client events (docs/46 D9, docs/01_DOMAIN.md §EDITOR_CHANGE).
 * Pure functions: the editor adapter passes plain change records, never editor objects.
 */

export type InputSource = "typing" | "paste" | "other";
export type OperationType = "INSERT" | "DELETE" | "REPLACE";

/** One text change, offsets relative to the content before the edit (Monaco's IModelContentChange). */
export interface TextChange {
  rangeOffset: number;
  rangeLength: number;
  text: string;
}

export interface EditorChangedPayload {
  [key: string]: unknown;
  operation_type: OperationType;
  range_offset: number;
  range_length: number;
  text: string;
  editor_version: string;
  input_source: InputSource;
}

export function operationType(c: TextChange): OperationType | null {
  if (c.rangeLength === 0) return c.text ? "INSERT" : null;
  return c.text ? "REPLACE" : "DELETE";
}

/**
 * One payload per change range, ordered by descending offset so that applying them one after
 * the other to the previous content reproduces the edit (multi-cursor edits share a version).
 * Diffs only, never the full content (REQ-TRACE-004).
 */
export function editorChangedPayloads(changes: readonly TextChange[], editorVersion: number, inputSource: InputSource): EditorChangedPayload[] {
  return [...changes]
    .sort((a, b) => b.rangeOffset - a.rangeOffset)
    .flatMap((c) => {
      const op = operationType(c);
      return op
        ? [{ operation_type: op, range_offset: c.rangeOffset, range_length: c.rangeLength, text: c.text, editor_version: String(editorVersion), input_source: inputSource }]
        : [];
    });
}

/** Applies EDITOR_CHANGED payloads in order (replay; used by tests and later by 20B). */
export function applyEditorChanges(content: string, payloads: readonly EditorChangedPayload[]): string {
  return payloads.reduce((s, p) => s.slice(0, p.range_offset) + p.text + s.slice(p.range_offset + p.range_length), content);
}

export const problemOpenedPayload = (problemId: string, language: string) => ({ problem_id: problemId, language });

export const checkpointPayload = (snapshotId: string) => ({ code_snapshot_id: snapshotId });

export const runRequestedPayload = (snapshotId: string, runId: string, input: string) => ({
  code_snapshot_id: snapshotId,
  run_id: runId,
  input_used: input,
});

export const runCompletedPayload = (r: {
  id: string;
  snapshot_id: string;
  status: string;
  verdict?: string | null;
  execution_time_ms?: number | null;
}) => ({
  run_id: r.id,
  code_snapshot_id: r.snapshot_id,
  status: r.status,
  verdict: r.verdict ?? null,
  execution_time_ms: r.execution_time_ms ?? null,
});

/** Line count sent with a snapshot (the server computes final_loc itself). */
export const lineCount = (content: string) => (content === "" ? 0 : content.split("\n").length);
