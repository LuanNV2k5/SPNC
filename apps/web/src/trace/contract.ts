import {
  checkpointPayload,
  editorChangedPayloads,
  problemOpenedPayload,
  runCompletedPayload,
  runRequestedPayload,
} from "./payloads";
import type { ClientEventType, TraceEvent } from "./types";

/**
 * One batch with every event type the client emits, built by the real payload builders
 * (docs/46 AC-20A-09). `contract-fixtures.json` holds the same batch; the backend test
 * `tests/api/test_phase20a_trace_contract.py` posts it to the real ingest endpoint after
 * replacing the {{…}} placeholders with ids it creates.
 */
export function contractEvents(): TraceEvent[] {
  const run = "{{RUN_ID}}";
  const runSnap = "{{RUN_SNAPSHOT_ID}}";
  const items: [ClientEventType, Record<string, unknown>][] = [
    ["PROBLEM_OPENED", problemOpenedPayload("{{PROBLEM_ID}}", "PYTHON3")],
    ...editorChangedPayloads([{ rangeOffset: 0, rangeLength: 0, text: "print(1)" }], 2, "typing").map((p) => ["EDITOR_CHANGED", p] as [ClientEventType, Record<string, unknown>]),
    ...editorChangedPayloads([{ rangeOffset: 6, rangeLength: 1, text: "40 + 2" }], 3, "paste").map((p) => ["EDITOR_CHANGED", p] as [ClientEventType, Record<string, unknown>]),
    ...editorChangedPayloads([{ rangeOffset: 0, rangeLength: 0, text: "\n" }, { rangeOffset: 12, rangeLength: 1, text: "" }], 4, "other").map((p) => ["EDITOR_CHANGED", p] as [ClientEventType, Record<string, unknown>]),
    ["SESSION_CHECKPOINT", checkpointPayload("{{CHECKPOINT_SNAPSHOT_ID}}")],
    ["RUN_REQUESTED", runRequestedPayload(runSnap, run, "1 2\n")],
    ["RUN_COMPLETED", runCompletedPayload({ id: run, snapshot_id: runSnap, status: "COMPLETED", verdict: "ACCEPTED", execution_time_ms: 12 })],
  ];
  return items.map(([event_type, payload], i) => ({
    sequence_number: i + 1,
    event_type,
    client_timestamp: new Date(Date.UTC(2026, 9, 30, 8, 0, i)).toISOString(),
    payload,
  }));
}
