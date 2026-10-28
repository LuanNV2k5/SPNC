# 34 — SESSION HARDENING (PHASE 08E) SPECIFICATION

> **Module:** Session Lifecycle (Phase 08E)
> **Status:** APPROVED 2026-10-28 (all §8 recommendations; see PROJECT_PROVENANCE_LOG.md) — IMPLEMENTATION IN PROGRESS
> **Date:** 2026-10-28
> **Parent Baseline:** `phase-08-signal-locked` (`a74e5d1`) + docs commit `7c7d9f9`
> **Proposed Branch:** `phase08e`
> **Target Lock Tag:** `phase-08e-session-hardening-locked`
> **Mandate:** `docs/PROJECT_PROVENANCE_LOG.md` — "GAP-08D-01 Scheduling" (APPROVED_SCOPE_DECISION, 2026-10-28)

---

## 1. Purpose

Close the session-termination requirements that Phase 05–08 left open:

| Requirement | Text (abridged) | Current state |
|---|---|---|
| **REQ-SIGNAL-001** | `Session.final_loc` = lines of code in the final snapshot; `SESSION_ENDED` carries `final_loc` | `coding_sessions` has no `final_loc` column |
| **REQ-TRACE-015** | On session end, record `SESSION_ENDED` with `final_loc`, `working_time`, `termination_actor` | No server-recorded `SESSION_ENDED`. A client *can* send one through trace ingest, unverified |
| **REQ-SESSION-002** | `termination_actor` ∈ {STUDENT, SYSTEM_EXAM_TIMEOUT, SYSTEM_SESSION_POLICY}, non-null when ENDED/ABANDONED | Column exists (`termination_source`), but the value is **chosen by the client** |
| Domain §1.4 Session entity | `working_time_seconds`, `final_loc` fields | Both missing |

Domain references: `docs/01_DOMAIN.md` line 142 (Session fields), line 182 (`SESSION_ENDED` payload: `final_code_snapshot_id`, `final_loc`, `working_time_seconds`, `termination_actor`), `docs/02_USE_CASES.md` UC-E02 step 11e–f.

---

## 2. Findings From the Current Code (2026-10-28)

| # | Finding | Location | Severity |
|---|---|---|---|
| F1 | `end_practice_session` / `end_exam_session` accept `termination_source` from the request body. A STUDENT can end their own session as `SYSTEM_EXAM_TIMEOUT` or `SYSTEM_SESSION_POLICY`, which corrupts the audit trail teachers rely on. | `app/services/academic.py:431`, `:494`; `EndSessionRequest` in `app/schemas/academic.py:262` | **HIGH** (integrity) |
| F2 | `SESSION_ENDED` is an ingestible client event type. A client can forge the end marker with arbitrary payload. | `TraceEventType` / `app/schemas/trace.py` | MEDIUM |
| F3 | `repo.end_session` only flips status and `ended_at`. It records no trace event and computes no `final_loc` or working time. | `app/repositories/academic.py:444` | requirement gap |
| F4 | Trace ingest takes no row lock on the session. A batch that passed the `ACTIVE` check can commit after the session ended. Once the server writes `SESSION_ENDED`, that becomes a `sequence_number` collision. | `app/services/trace.py:31` | MEDIUM (race) |
| F5 | `abandon_session` exists but nothing calls it. No stale-session policy runs. | `app/repositories/academic.py:452` | out of scope (§3.2) |
| F6 | `LOC_ANOMALY` candidates include sessions of any status, so ENDED sessions produce signals with `final_loc = null` even after the session has a final LOC. | `app/services/judge/materializer.py` `_process_loc_sessions` | decision D7 |

---

## 3. Scope

### 3.1 In Scope
1. **S1 — Schema:** new migration (down_revision `c4819d7a2e10`) adding to `coding_sessions`:
   - `final_loc INTEGER NULL CHECK (final_loc >= 0)`
   - `working_time_seconds INTEGER NULL CHECK (working_time_seconds >= 0)`
   - `final_code_snapshot_id UUID NULL REFERENCES code_snapshots(id) ON DELETE RESTRICT`
   - No historical migration is modified.
2. **S2 — Single finalization path:** `SessionLifecycleService.finalize(db, session, status, actor)` is the only code that moves a session out of `ACTIVE`. All three paths use it: practice end, exam end, and `abandon_session` (kept for future policy use). In one transaction it:
   1. locks the session row (`SELECT … FOR UPDATE`) and re-checks `status == ACTIVE` (409 `SESSION_ALREADY_ENDED` otherwise);
   2. selects the final snapshot: latest `CodeSnapshot` of the session by `created_at DESC, id DESC`;
   3. computes `final_loc` with the same non-blank-line policy as `LOC_ANOMALY` (`signals._count_loc`, moved to a shared helper), or `null` if there is no snapshot (D3);
   4. sets `ended_at = now()` (server clock) and `working_time_seconds` per D1;
   5. appends a server-authored `SESSION_ENDED` `TraceEvent` with `sequence_number = max(sequence_number) + 1` (or 1), `client_timestamp = server_timestamp = ended_at`, and payload:
      ```json
      {
        "source": "SERVER",
        "final_code_snapshot_id": "UUID or null",
        "final_loc": 42,
        "working_time_seconds": 1830,
        "termination_actor": "STUDENT"
      }
      ```
   6. writes `status`, `termination_source`, `ended_at`, `final_loc`, `working_time_seconds`, `final_code_snapshot_id`, then commits.
3. **S3 — Actor integrity (F1):** student endpoints always record `STUDENT`. `EndSessionRequest.termination_source` is removed from the effective contract (D5). `SYSTEM_*` actors can only come from internal callers.
4. **S4 — Reserved event type (F2):** trace ingest rejects `event_type = SESSION_ENDED` with 422 `TRACE_EVENT_TYPE_RESERVED` (D4). Exact-duplicate retries of events already stored are unaffected.
5. **S5 — Ingest/finalize serialization (F4):** ingest takes `SELECT … FOR KEY SHARE` on the session row before its `ACTIVE` check:
   - it conflicts with finalize's `FOR UPDATE`, so the two serialize;
   - it does **not** conflict with the signal outbox worker's `FOR NO KEY UPDATE SKIP LOCKED`, so live ingestion still never waits on the signal engine (preserves the Phase 08D guarantee).
6. **S6 — Flush guard (D6, optional):** the end request may carry `last_sequence_number`. If the server's highest stored sequence is lower, finalize returns 409 `TRACE_NOT_FLUSHED` and the client flushes, then retries. This keeps client events from being dropped behind the server's `SESSION_ENDED`.

### 3.2 Out of Scope (fenced)
- **REQ-SESSION-003** server-side exam timeout sweeper, and **REQ-SESSION-004** auto-submission from the latest snapshot. There is no exam scheduler and no Submission creation/judging pipeline yet (D8). The `finalize` service is designed so a future sweeper calls it with `SYSTEM_EXAM_TIMEOUT`.
- Stale-session ABANDONED policy scheduler (F5), and OQ-01 (practice session resume semantics).
- Backfilling `SESSION_ENDED` events for sessions that are already ENDED. Trace is append-only and the server must not fabricate history (D9).
- Any Phase 09 surface: teacher observation endpoints, annotations, WebSocket, UI.

---

## 4. Interaction With the Signal Engine
- `SESSION_ENDED` is not a meaningful event. The outbox trigger ignores it, and IDLE behaviour is unchanged.
- Signals already stored keep their evidence unchanged (DCR SPNC_LOC_EVIDENCE_CONTRACT immutability).
- D7 decides whether a `LOC_ANOMALY` **created after** finalization should carry `final_loc = session.final_loc`.
- `rule_version` stays `"1.0.0"` unless D7 changes evaluator output. If it does, bump it to `"1.1.0"` (REQ-SIGNAL-005 traceability).

---

## 5. API Contract Changes

| Endpoint | Change |
|---|---|
| `POST /api/v1/my/practice/sessions/{id}/end` | Body `termination_source` ignored or rejected (D5); optional `last_sequence_number` (D6). Response adds `final_loc`, `working_time_seconds`, `final_code_snapshot_id`. |
| `POST /api/v1/my/exam-sessions/{id}/end` | Same as above. |
| `POST /api/v1/my/coding-sessions/{id}/trace-events/batch` | `SESSION_ENDED` in a batch → 422 `TRACE_EVENT_TYPE_RESERVED` (D4). |
| Teacher trace replay endpoints | No change. The server `SESSION_ENDED` appears as the last event, with `payload.source = "SERVER"`. |

All errors keep the `{error_code, message, request_id}` envelope (PROJECT_RULES #29).

---

## 6. Acceptance Criteria

| ID | Criterion | Test |
|---|---|---|
| AC-08E-01 | Fresh DB migrates base → new head; downgrade to `c4819d7a2e10` removes the three columns | alembic up/down on disposable PostgreSQL |
| AC-08E-02 | Ending a session with snapshots sets `final_loc` = non-blank lines of the latest snapshot and `final_code_snapshot_id` to it | `tests/api/test_session_lifecycle.py` (new) |
| AC-08E-03 | Ending a session with no snapshot sets `final_loc = null`, `final_code_snapshot_id = null`; no code is fabricated | same |
| AC-08E-04 | Exactly one `SESSION_ENDED` event exists, with `sequence_number = previous max + 1` and the full payload of §3.1 S2.5 | same |
| AC-08E-05 | `working_time_seconds` ≥ 0, computed from server timestamps only (REQ-TRACE-006), per D1 | same |
| AC-08E-06 | STUDENT sending `termination_source = SYSTEM_EXAM_TIMEOUT` cannot produce that actor | same |
| AC-08E-07 | Ingest of a `SESSION_ENDED` event → 422 `TRACE_EVENT_TYPE_RESERVED`; exact-duplicate retry of stored events still succeeds | `tests/api/test_trace.py` (extended) |
| AC-08E-08 | Concurrent ingest + end (barrier-synchronised) never yields a sequence collision or an event after `SESSION_ENDED` | `tests/api/test_session_concurrency.py` (new) |
| AC-08E-09 | Outbox worker holding its claim does not block ingest (Phase 08D regression) | `test_scheduler_idle.py::test_c_idle_live_ingestion_not_blocked_by_worker` |
| AC-08E-10 | Second end call → 409 `SESSION_ALREADY_ENDED`; no second event | same as AC-08E-02 |
| AC-08E-11 | Full regression: Phase 03–08 suites pass on fresh databases | pytest |
| AC-08E-12 | Scope fence: no teacher/Phase 09 routes, no UI files, no exam sweeper | `git diff phase-08-signal-locked` |

---

## 7. Implementation Plan (files)

| Step | Files |
|---|---|
| 1. Migration + model fields | `alembic/versions/<new>_phase08e_session_finalization.py`, `app/models/session.py` |
| 2. Shared LOC helper | `app/services/loc.py` (new, `count_loc`); `app/services/judge/signals.py` imports it |
| 3. Lifecycle service | `app/services/session_lifecycle.py` (new), `app/repositories/academic.py` (`end_session`/`abandon_session` delegate or are replaced) |
| 4. Endpoint/schema wiring | `app/services/academic.py`, `app/schemas/academic.py` (`EndSessionRequest`, `SessionResponse`) |
| 5. Ingest hardening | `app/services/trace.py`, `app/repositories/trace.py` |
| 6. (D7 only) LOC evidence | `app/services/judge/signals.py`, `config.SIGNAL_RULE_VERSION` |
| 7. Tests | new `test_session_lifecycle.py`, `test_session_concurrency.py`; extend `test_trace.py`, `test_academic.py` |
| 8. Docs | this file §9 verification record; `docs/33` §10 GAP-08D-01 → RESOLVED |

Router stays thin and the business logic lives in services (PROJECT_RULES #6–7).

---

## 8. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | What is `working_time_seconds`? Requirements only say "≥ 0, server timestamps". | (a) `ended_at − opened_at` (wall clock); (b) wall clock minus IDLE gaps ≥ threshold | **(a)**. Factual and unambiguous. (b) builds an interpretation into a stored fact, and teachers already see IDLE signals separately. |
| **D2** | Line-counting policy for `final_loc` | (a) non-blank lines (same as `LOC_ANOMALY`); (b) `CodeSnapshot.line_count` as recorded | **(a)**. One LOC definition system-wide, computed by the server rather than trusted from the client. |
| **D3** | Session ended with no snapshot | (a) `final_loc = null`; (b) `0` | **(a)**. `0` would claim "empty code" without evidence (cf. REQ-SESSION-004 "no fabricate"). |
| **D4** | Client-sent `SESSION_ENDED` in trace ingest | (a) reject 422; (b) accept but ignore for lifecycle | **(a)**. A single authoritative end marker. This is a Phase 06 ingest contract change and needs explicit approval. |
| **D5** | `termination_source` in student end requests | (a) reject non-STUDENT with 422; (b) silently force STUDENT | **(a)**. Surfaces client bugs and leaves no silent coercion. |
| **D6** | Flush guard `last_sequence_number` | (a) implement (optional field); (b) skip | **(a)**. Prevents losing in-flight edits behind the end marker. Cheap. |
| **D7** | `LOC_ANOMALY` created after finalization | (a) fill `final_loc = session.final_loc` for new signals only, bump `rule_version` to 1.1.0; (b) leave as is | **(a)**. Fulfils REQ-SIGNAL-002's `final_loc` evidence field without mutating stored evidence. |
| **D8** | Include REQ-SESSION-003/004 (exam timeout sweeper + auto-submit) | (a) separate phase once the Submission pipeline exists; (b) include sweeper only | **(a)**. Depends on Submission creation and judging, which do not exist. |
| **D9** | Already-ENDED historical sessions | (a) leave `final_loc`/event null; (b) backfill columns only (no event) | **(a)**. Avoids retro-writing facts the system did not record at end time. |

Approval of this document (all recommendations, or with per-decision overrides) is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before implementation starts (PROJECT_RULES #1–3).

---

## 9. Verification Record

*To be completed at Phase 08E closure.*
