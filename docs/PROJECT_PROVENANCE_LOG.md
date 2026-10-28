# Project Provenance Log

## Incident: Historical QA report artifact loss

Date:
2026-09-21

Affected files:

- PHASE_03_AUTH_RBAC_BUILD_REPORT.md
- PHASE_03_INDEPENDENT_QA_REPORT.md
- PHASE_03_INDEPENDENT_QA_REPORT_FINAL.md
- PHASE_03_REMEDIATION_REPORT.md
- PHASE_04_REMEDIATION_REPORT_1.md

Status for each:

LOST_UNTRACKED_ARTIFACT

Cause:

An overly broad QA cleanup command matching PHASE_* removed the files.

Recovery:

Exact copies were searched for in the local repository and available
Antigravity brain/report directories.

No exact surviving copies were found.

Important provenance statement:

- These reports were untracked artifacts.
- They were not members of the locked Phase03 or Phase04 commits.
- Their loss does not modify the locked source/test/migration history.
- Historical Git tags remain authoritative for locked baselines.
- Original report contents are NOT reconstructed or fabricated.
- Future audits must treat the original report contents as unavailable.

Authoritative effective baseline tags:
- phase-03-auth-rbac-complete: d4d496be0e4785f5fc88f231486a759220c42c00
- phase-04-admin-locked: 27b0fc8c15a0734c810f7cb4b2479f6eaa8cdc0f
- phase-05-academic-locked: a92af65361ce62c62df7a50e75b347e6b55f18b5

Future cleanup policy:

- Never use broad deletion patterns such as PHASE_*.
- Never use git clean for project QA cleanup.
- Temporary QA files must be explicitly named and removed individually.
- Historical reports/artifacts must be classified before deletion.
- Git locked tags/commits remain the authoritative implementation
  provenance.
- Untracked reports are supplementary evidence only.

---

## Decision: DCR SPNC_RF_RUN_EVIDENCE_CONTRACT (REPEATED_FAILURE Evidence Schema)

Date:
2026-10-23

Status:
APPROVED_DOMAIN_AMENDMENT

Approval Source:
Project Owner explicit authorization

Scope:
- `docs/01_DOMAIN.md` §1.8:277, §6 (Revision 0.4)
- `docs/33_ATTENTION_SIGNAL_ARCHITECTURE.md` §4.3:148-150, §9.4 (GAP-08D-04)

Context:
`REPEATED_FAILURE` originally specified `submission_count` in `docs/01_DOMAIN.md` §1.8, conflicting with §1.6:129 ("Verdict không tự động sinh attention signal"). In practice, repeated execution failures in the web IDE occur during trial sandbox executions (`Run`), not formal summative submissions (`Submission`).

Old Contract:
`{problem_id, submission_count, failed_count, verdicts[], time_range_start, time_range_end}`

New Approved Contract:
`{problem_id, target_entity, run_count, failed_count, verdicts[], time_range_start, time_range_end}`
where `target_entity` is strictly `"RUN"`.

Requirement Impact:
- Preserves `REQ-SIGNAL-003` (verifiable non-null evidence matching domain §1.8).
- Preserves `REQ-SIGNAL-004` (non-judgmental factual wording).
- Preserves `REQ-SIGNAL-005` (traceability via `rule_version`).
- Preserves domain invariant `DI-13` / `DTI-13` (distinct `Run` vs `Submission` lifecycles).

Compatibility Risks:
- Zero breaking changes to active APIs (no callers currently consume `submission_count`).
- Zero database schema or migration impact (`evidence` is a PostgreSQL `JSONB` column).
- Zero historical record mutation. All legacy Phase 08 diagnostic fields preserved.

Planned Independent QA:
Unit 1B-2B TDD test suite validating canonical schema, types, chronological order, and entity isolation.

---

## Decision: DCR SPNC_LOC_EVIDENCE_CONTRACT (LOC_ANOMALY Evidence Schema)

Date:
2026-10-24

Status:
APPROVED_DOMAIN_AMENDMENT

Approval Source:
Project Owner explicit authorization

Scope:
- `docs/01_DOMAIN.md` §1.8:276, §6 (Revision 0.5)
- `docs/33_ATTENTION_SIGNAL_ARCHITECTURE.md` §4.4:174-176, §9.4 (GAP-08D-04)

Context:
`LOC_ANOMALY` specified `{session_id, final_loc, context_median_loc, delta, threshold_relative}` in `docs/01_DOMAIN.md` §1.8. In real-time background evaluation of active sessions, intermediate snapshot code lines cannot truthfully be labeled `final_loc`. Setting `final_loc = student_loc` during active coding violates domain truthfulness and conflicts with `REQ-SIGNAL-001` / `REQ-TRACE-015`, which bind `final_loc` exclusively to session termination (`SESSION_ENDED`).

Old Contract:
`{session_id, final_loc, context_median_loc, delta, threshold_relative}`

New Approved Contract:
`{session_id, observed_loc, context_median_loc, delta, threshold_relative, final_loc}`

Approved Semantics & Decisions:
- `observed_loc`: Non-blank LOC measured from the evaluated `CodeSnapshot`.
- `final_loc`: Nullable (`Optional[int]`), strictly null for `ACTIVE` sessions.
- Evidence Immutability: Once persisted, `AttentionSignal.evidence` is immutable. A later `SESSION_ENDED` event must never retroactively modify previously stored evidence records.
- `delta`: Factual line difference `observed_loc - context_median_loc`, measured in lines.
- Relative Qualification Policy: Anomaly qualification remains strictly based on relative cohort deviation (`relative_dev > settings.SIGNAL_LOC_DEVIATION_MULTIPLIER`), never an absolute LOC threshold.
- Zero-Median Policy: When cohort median is zero (`context_median_loc <= 0.0`), relative ratio is undefined and `evaluate_loc_anomaly` returns `None` (zero-median generates no signal).
- Peer Privacy: Zero peer student IDs, usernames, or source code snippets in evidence; only scalar aggregate statistics (`context_median_loc`, `cohort_size`).
- Versioning Policy: Preserves `rule_version = "1.0.0"` because the current qualification algorithm and relative threshold logic are unchanged.
- Open Requirements: `REQ-SIGNAL-001` and `REQ-TRACE-015` remain OPEN until session final LOC and `SESSION_ENDED` handling are implemented in Phase 08 closure / Session Hardening.

Requirement Impact:
- Preserves `REQ-SIGNAL-002` (relative cohort median deviation, no hardcoded absolute thresholds).
- Preserves `REQ-SIGNAL-003` (verifiable non-null evidence matching domain §1.8).
- Preserves `REQ-SIGNAL-004` (non-judgmental factual wording).
- Preserves `REQ-SIGNAL-005` (traceability via `rule_version="1.0.0"`).
- Leaves `REQ-SIGNAL-001` and `REQ-TRACE-015` open for subsequent session lifecycle implementation.

Compatibility Risks:
- Zero breaking changes to active APIs.
- Zero database schema or migration impact (`evidence` is a PostgreSQL `JSONB` column).
- Zero historical record mutation. All legacy Phase 08 diagnostic fields preserved (`student_loc`, `cohort_median_loc`, `cohort_size`, `relative_deviation`, `configured_threshold`, `loc_counting_policy`).

Planned Independent QA:
Unit 1B-2C TDD test suite validating canonical schema, types, nullable `final_loc` on active sessions, mathematical `delta`, zero-median handling, peer privacy, and entity isolation.

---

## Decision: DCR SPNC_IDLE_HISTORICAL_GAP_CONTRACT (GAP-08D-03 Ratification)

Date:
2026-10-28

Status:
APPROVED_IMPLEMENTATION_RATIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-28, after review of the Phase 08D verification record)

Scope:
- `docs/33_ATTENTION_SIGNAL_ARCHITECTURE.md` §4.1, §9 (REQ-IDLE-001), §10 (GAP-08D-03), §14 item 3
- Locked implementation: tag `phase-08-signal-locked` (`a74e5d17f5bba85a04c07a5b1197fc95fe5607b3`)

Context:
GAP-08D-03 asked whether active-session (ongoing) idle monitoring alone satisfies `REQ-IDLE-001`. The baseline defines the idle interval as the `server_timestamp` gap between two consecutive meaningful events (`docs/01_DOMAIN.md` §1.7.4, DTI-09; `docs/02_USE_CASES.md` UC-E03; `docs/03_REQUIREMENTS.md` REQ-IDLE-001). Active-tail monitoring alone does not cover gaps that are already closed. Phase 08D implemented closed-gap detection and was locked pending this ratification.

Ratified Contract:
- Meaningful event set for IDLE is exactly `EDITOR_CHANGED`, `RUN_REQUESTED`, `SUBMISSION_CREATED` (Phase 06 enums for EDITOR_CHANGE, RUN_EXECUTED, SUBMISSION_MADE). `SESSION_CHECKPOINT` is a timeline marker (`docs/01_DOMAIN.md` B15) and does not reset inactivity.
- Two detection modes:
  1. Active tail (`evaluate_idle_detected`): ongoing inactivity of `ACTIVE` sessions.
  2. Closed historical gap (`evaluate_historical_idle_gaps` via `trace_signal_outbox`, migration `c4819d7a2e10`): gaps between consecutive meaningful events (or `opened_at` and the first one), for sessions in any status. Evaluated only up to the highest contiguous `sequence_number`.
- Overlap policy: both modes share the first-window dedup key `IDLE:{session_id}:{int(start)}:W1`. One idle episode yields one W1 alert. Evidence stored first is immutable and is never rewritten by the later closing event.
- Evidence carries the canonical `{start_time, end_time, duration_seconds, meaningful_event_before_id, threshold_used}` plus legacy diagnostic keys. `rule_version = "1.0.0"`.

Requirement Impact:
- Satisfies `REQ-IDLE-001` (consecutive meaningful-event gaps) and `REQ-IDLE-002` (canonical evidence).
- Preserves `REQ-IDLE-003` / `REQ-SIGNAL-004` (factual wording), `REQ-SESSION-005` (session status never mutated) and DTI-09.
- No change to `docs/01_DOMAIN.md`, `docs/03_REQUIREMENTS.md` or `rule_version`.

Compatibility Risks:
- No API change. Schema change is limited to the additive `trace_signal_outbox` table and trigger (migration `c4819d7a2e10`). No historical migration is modified.
- Bootstrap enqueues existing meaningful events idempotently (`ON CONFLICT (event_id) DO NOTHING`).

Verification Evidence:
Phase 08D verification record, `docs/33_ATTENTION_SIGNAL_ARCHITECTURE.md` §15.2: Phase 08 suite 89 passed; Phase 03-07 regression 262 passed on fresh PostgreSQL 16.

Still Open:
- GAP-08D-01 (`CodingSession.final_loc`, `REQ-SIGNAL-001`, `REQ-TRACE-015`) is not covered by this decision and remains OPEN_DECISION.

---

## Decision: GAP-08D-01 Scheduling (Session Final LOC)

Date:
2026-10-28

Status:
APPROVED_SCOPE_DECISION

Approval Source:
Project Owner explicit authorization (2026-10-28): option "Session Hardening".

Decision:
`REQ-SIGNAL-001` (`CodingSession.final_loc`) and `REQ-TRACE-015` (server-recorded `SESSION_ENDED` with `final_loc`, `working_time_seconds`, `termination_actor`) are implemented in a dedicated sub-phase **Phase 08E — Session Hardening**. It runs after `phase-08-signal-locked` and before Phase 09. They are not deferred to Phase 09.

Constraints:
- Requires a new Alembic migration after `c4819d7a2e10`. Historical migrations stay untouched (PROJECT_RULES #4–5).
- Already-stored `AttentionSignal.evidence` stays immutable. `LOC_ANOMALY.final_loc` stays null on signals created while the session was active (DCR SPNC_LOC_EVIDENCE_CONTRACT).
- Specification: `docs/34_SESSION_HARDENING.md`. Implementation starts only after that specification is approved.

---

## Decision: Phase 08E Session Hardening Specification Approval

Date:
2026-10-28

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-28): "Duyệt theo khuyến nghị". All recommendations in `docs/34_SESSION_HARDENING.md` §8 are approved without overrides.

Approved Decisions:
- D1 `working_time_seconds = ended_at − opened_at` (server wall clock).
- D2 `final_loc` = non-blank lines of the final snapshot (same policy as `LOC_ANOMALY`).
- D3 No snapshot → `final_loc = null`, `final_code_snapshot_id = null`.
- D4 Trace ingest rejects client `SESSION_ENDED` (422 `TRACE_EVENT_TYPE_RESERVED`). This is an approved Phase 06 ingest contract change.
- D5 Student end requests with non-STUDENT `termination_source` → 422.
- D6 Optional `last_sequence_number` flush guard → 409 `TRACE_NOT_FLUSHED`.
- D7 `LOC_ANOMALY` created after finalization carries `final_loc = session.final_loc`; `rule_version` → `"1.1.0"`. Stored evidence is not mutated.
- D8 REQ-SESSION-003/004 excluded from 08E (requires Submission pipeline).
- D9 No backfill for sessions ended before 08E.

---

## Decision: Phase 09 Teacher Observation Specification Approval

Date:
2026-10-28

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-28): "Duyệt theo khuyến nghị". All recommendations in `docs/35_TEACHER_OBSERVATION.md` §9 are approved without overrides.

Approved Decisions:
- D1 `SignalStatus` = `NEW | ACKNOWLEDGED | DISMISSED` (domain §1.8). TEACHER OWN_CLASS may move NEW → ACKNOWLEDGED/DISMISSED and back to NEW. See DCR SPNC_SIGNAL_STATUS_TRANSITIONS below.
- D2 Session visibility in class context (docs/35 §3): exam assigned to the class, or practice problem published to the class / owned by the teacher. Applies to the Phase 06 teacher trace/scratchpad endpoints and teacher run reads.
- D3 Timeline order = `sequence_number` (causal client order), with `server_timestamp` on every event. This is the approved interpretation of REQ-OBS-003 "theo server_timestamp".
- D4 Cross-process WebSocket notifications via PostgreSQL `LISTEN/NOTIFY` triggers (id-only payloads).
- D5 REQ-OBS-007 statistics deferred until the Submission pipeline exists.
- D6 `EXPIRED` / `CANCELLED` participation states derived in responses; no enum change.
- D7 TeacherAnnotation soft delete (`deleted_at`).
- D8 Annotation content: plain text, 1–5000 characters.
- D9 ADMIN observation endpoints deferred to a later admin phase.

---

## Decision: DCR SPNC_SIGNAL_STATUS_TRANSITIONS

Date:
2026-10-28

Status:
APPROVED_RBAC_AMENDMENT

Approval Source:
Project Owner explicit authorization (2026-10-28), docs/35 D1.

Scope:
- `docs/05_RBAC_MATRIX.md` Resource AttentionSignal (Revision 0.4)
- `apps/api/app/models/observation.py` `SignalStatus`

Change:
- Old: the RBAC matrix lists only ACKNOWLEDGE (TEACHER OWN_CLASS). Code enum is `NEW / VIEWED / ACK / DISMISSED`.
- New: the code enum matches domain §1.8, `NEW / ACKNOWLEDGED / DISMISSED`. TEACHER OWN_CLASS may also DISMISS or reopen to NEW. Every change writes an AuditLog entry. Evidence stays immutable (DTI-08).

Compatibility:
- `attention_signals.status` is `String(20)`. Before Phase 09 only `NEW` was ever written, so no stored rows change.

---

## Decision: Phase 10 Submission & Exam Lifecycle Specification Approval

Date:
2026-10-28

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-28): "Duyệt theo khuyến nghị". All recommendations D1–D14 in `docs/36_SUBMISSION_AND_EXAM_LIFECYCLE.md` §9 are approved without overrides.

Approved Decisions (summary):
D1 no snapshot → no Submission; D2 submit ends the session; D3 normalized output comparison; D4 first-failing verdict + weighted score; D5 best submission per exam problem; D6 no automatic re-judge; D7 sample-only detail for students; D8 enums aligned to domain; D9 no rate limit; D10 separate exam scheduler daemon; D11 status + time window for exam access; D12 per-problem judge limits capped by global maxima; D13 admin cancel limited to DRAFT/SCHEDULED until OQ-23; D14 result visibility (practice always, exam after ENDED + `allow_view_result_after`).

---

## Decision: DCR SPNC_SUBMISSION_REQUIRES_SNAPSHOT

Date:
2026-10-28

Status:
APPROVED_DOMAIN_AMENDMENT

Approval Source:
Project Owner explicit authorization (2026-10-28), docs/36 D1.

Scope:
`docs/01_DOMAIN.md` §1.6 (Revision 0.6)

Change:
- Old: "Nếu code_snapshot_id null … Submission vẫn được tạo với trạng thái rõ ràng".
- New: no Submission is created when the server received no snapshot before timeout.

Reason:
§1.6 contradicted UC-E02 A3 and REQ-SESSION-004, which both forbid creating a submission without server-received code. A null-code submission also cannot be judged.

Compatibility:
- No stored data affected: no Submission rows are created by pre-Phase 10 code.
- `submissions.snapshot_id` stays NOT NULL.

---

## Decision: DCR SPNC_ADMIN_CANCEL_SCOPE

Date:
2026-10-28

Status:
APPROVED_BEHAVIOUR_CORRECTION

Approval Source:
Project Owner explicit authorization (2026-10-28), docs/36 D13.

Change:
`PATCH /api/v1/admin/exams/{id}/cancel` only accepts DRAFT/SCHEDULED exams. ONGOING returns 409 `EXAM_ONGOING_CANCEL_UNDECIDED` until OQ-23 is decided.

Reason:
Phase 04 allowed ADMIN to cancel ONGOING exams. That contradicts OQ-23's current assumption and `00_SCOPE.md` NG12.

---

## Decision: Phase 11 Shared Storage & Compose Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all". All recommendations D1–D6 in `docs/37_SHARED_STORAGE_AND_COMPOSE.md` §6 are approved without overrides.

Approved Decisions (summary):
D1 `minio` client library; D2 `STORAGE_BACKEND=memory|s3`, default memory; D3 host Docker socket mounted into the worker container for the demo/dev stack only, production isolation tracked as OQ-26; D4 first admin via CLI bootstrap, no default credentials; D5 `websockets` dependency; D6 upload failure → 503 `STORAGE_UNAVAILABLE`.

Scope note:
Implements the already-approved architecture (docs/07, docs/10, ADR-007). No requirement, endpoint contract or schema change.

---

## Decision: Phase 12 MUST Gap Closure Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all". All recommendations D1–D11 in `docs/38_MUST_GAP_CLOSURE.md` §7 are approved without overrides.

Approved Decisions (summary):
D1 8-char unambiguous random invite code; D2 owner can rotate it; D3 removed member re-joins by re-activation; D4 problem fields and test cases locked in SCHEDULED/ONGOING exams; D5 problem soft delete; D6 exam edits DRAFT-only except `allow_view_result_after`; D7 `duration_minutes` = per-student limit, deadline `min(started_at + duration, end_time)` (OQ-27); D8 exam-session writes after the deadline → 403; D9 Run row is the RUN_EXECUTED record, runs shown in the teacher timeline; D10 `first_code_at` recorded at the first EDITOR_CHANGED; D11 `SUBMISSION_CREATED` reserved from client ingest.

---

## Decision: DCR SPNC_PROBLEM_LOCK_SCOPE

Date:
2026-10-29

Status:
APPROVED_BEHAVIOUR_CORRECTION

Approval Source:
Project Owner explicit authorization (2026-10-29), docs/38.

Change:
Problem fields and all test-case writes are rejected (409 `PROBLEM_IN_ACTIVE_EXAM`) while the problem is attached to a SCHEDULED or ONGOING exam (docs/38 D4).

Reason:
REQ-PROB-004. Phase 10A blocked test-case edits only while ONGOING, so a SCHEDULED exam's validated test cases could still change.

Compatibility:
Phase 10A test-case edits on SCHEDULED exams are now refused; error code `PROBLEM_IN_ONGOING_EXAM` is replaced by `PROBLEM_IN_ACTIVE_EXAM`.

---

## Decision: DCR SPNC_RUN_EXECUTED_RECORD

Date:
2026-10-29

Status:
APPROVED_BEHAVIOUR_CORRECTION

Approval Source:
Project Owner explicit authorization (2026-10-29), docs/38.

Change:
REQ-TRACE-011's `RUN_EXECUTED` is the persisted `Run` row (snapshot, input, output, verdict, error, execution time). No server trace event is written on run completion; the client's `RUN_REQUESTED` stays the meaningful event. The teacher timeline includes the session's runs (docs/38 D9).

Reason:
While a session is open the client owns `sequence_number`; a server event would collide with it, and runs can finish after `SESSION_ENDED`, which must stay the last event.

Compatibility:
No stored data changes. Timeline responses gain a `runs` list.

---

## Decision: DCR SPNC_FIRST_CODE_FACT

Date:
2026-10-29

Status:
APPROVED_BEHAVIOUR_CORRECTION

Approval Source:
Project Owner explicit authorization (2026-10-29), docs/38.

Change:
REQ-TRACE-002's `FIRST_CODE_INPUT` is recorded as `coding_sessions.first_code_at` (server clock) at the first ingested `EDITOR_CHANGED`, set once; no separate event (docs/38 D10).

Reason:
Same sequence-ownership constraint as SPNC_RUN_EXECUTED_RECORD; the column enforces once-per-session.

Compatibility:
Existing sessions keep `first_code_at = null` (not backfilled from history).

---

## Decision: DCR SPNC_RESERVED_SUBMISSION_EVENT

Date:
2026-10-29

Status:
APPROVED_BEHAVIOUR_CORRECTION

Approval Source:
Project Owner explicit authorization (2026-10-29), docs/38.

Change:
Client trace ingest rejects `SUBMISSION_CREATED` with 422 `TRACE_EVENT_TYPE_RESERVED`, like `SESSION_ENDED` (docs/38 D11).

Reason:
Since Phase 10A the server writes `SUBMISSION_CREATED` in the submit transaction; a client copy would be a fake submission marker.

Compatibility:
Phase 06 clients sending that type now get 422. No stored data changes.
