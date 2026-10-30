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

---

## Decision: Phase 13 Backend Completion Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all". All recommendations D1–D6 in `docs/39_BACKEND_COMPLETION.md` §7 are approved without overrides.

Approved Decisions (summary):
D1 content-addressed snapshot key `snapshots/{session_id}/{sha256}.txt`, UNIQUE on `object_key` dropped; D2 orphan sweep in the reconciler (grace 24 h, hourly, batch 500); D3 idle threshold captured per session at creation; D4 client-driven checkpoint cadence advertised in trace-state; D5 invalid `SESSION_CHECKPOINT` rejected; D6 practice list = PUBLIC + own-class CLASS problems.

---

## Decision: DCR SPNC_SNAPSHOT_CONTENT_KEY

Date:
2026-10-29

Status:
APPROVED_BEHAVIOUR_CORRECTION

Approval Source:
Project Owner explicit authorization (2026-10-29), docs/39.

Change:
New snapshot blobs use `snapshots/{session_id}/{sha256}.txt`; `code_snapshots.object_key` is no longer UNIQUE, so several snapshot rows may reference one immutable blob (docs/39 D1).

Reason:
With the Phase 06 key (`…/0_{sha256[:8]}.txt`) plus the UNIQUE constraint, a second snapshot of identical code in one session failed with 500 (reproduced 2026-10-29), blocking Run/Submit of unchanged code.

Compatibility:
Existing rows keep their old keys and stay readable. No data migration of blobs.

---

## Decision: DCR SPNC_CHECKPOINT_LINKAGE

Date:
2026-10-29

Status:
APPROVED_BEHAVIOUR_CORRECTION

Approval Source:
Project Owner explicit authorization (2026-10-29), docs/39.

Change:
Client trace ingest rejects a `SESSION_CHECKPOINT` whose `payload.code_snapshot_id` is not a CHECKPOINT snapshot of the same session (422 `CHECKPOINT_SNAPSHOT_INVALID`, batch refused) (docs/39 D5).

Reason:
REQ-TRACE-013 requires the event to reference its snapshot; Phase 06 accepted any payload.

Compatibility:
Phase 06 clients sending unlinked checkpoints now get 422. Stored events are not modified.

---

## Decision: Phase 10–13 Lock

Date:
2026-10-29

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-29): "Khóa Phase 10–13".

Locked Baselines:
| Phase | Spec | Lock commit | Tag | Verification |
|---|---|---|---|---|
| 10 Submission & exam lifecycle | docs/36 | `391a5bc` | `phase-10-submission-locked` | 469 passed (Phase 03–10) |
| 11 Shared storage & compose | docs/37 | `f94fb85` | `phase-11-infra-locked` | 476 passed, MinIO adapter 6, compose E2E 4 |
| 12 MUST gap closure | docs/38 | `f636a37` | `phase-12-must-gaps-locked` | 499 passed, compose E2E 4 |
| 13 Backend completion | docs/39 | this commit | `phase-13-backend-complete-locked` | 511 passed, compose E2E 4 |

Lineage:
Each phase branch was merged forward into the next (phase10 → phase11 → phase12 → phase13) after its lock commit, so commit hashes recorded in docs/36–39 are unchanged. Tags are local; nothing was pushed.

Open after lock:
OQ-16 (points, blocks REQ-STU-004), OQ-26 (production judge isolation), OQ-27 (`duration_minutes` meaning), frontend.

---

## Decision: OQ-16, OQ-26, OQ-27 Resolution (Phase 14)

Date:
2026-10-29

Status:
APPROVED_DECISION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all". Recommendations Q1–Q5 in `docs/40_OPEN_QUESTION_DECISIONS.md` §5 are approved without overrides.

Decisions:
- Q1–Q3 (OQ-16, REQ-STU-004): practice-only points, once per problem at the first ACCEPTED submission, EASY 10 / MEDIUM 20 / HARD 30 / none 10; cumulative, never reset; no leaderboard; exam submissions never award points.
- Q4 (OQ-26): dedicated judge VM with its own Docker daemon, gVisor runtime for sandboxes, least-privilege PostgreSQL role for the worker; the socket-mount compose stack remains demo/dev only.
- Q5 (OQ-27): deadline = min(started_at + duration_minutes, end_time); confirms docs/38 D7.

---

## Decision: Phase 14 Lock

Date:
2026-10-29

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-29): "Lock Phase 14".

Locked Baseline:
| Phase | Spec | Lock commit | Tag | Verification |
|---|---|---|---|---|
| 14 Open-question decisions (points, judge isolation, duration) | docs/40 | this commit | `phase-14-open-questions-locked` | 527 passed (Phase 03–14), compose E2E 4 |

Tag is local; nothing was pushed.

---

## Decision: Open Question Review (Step 0) — OQ-01…13, 15, 23, 24

Date:
2026-10-29

Status:
APPROVED_DECISION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all". Recommendations R1–R10 in `docs/41_OPEN_QUESTION_REVIEW.md` §4 are approved without overrides.

Decisions:
- R1 OQ-02: 5 failed logins / 15 min per username + IP → 429, no lockout.
- R2 OQ-05: no self role/status change by an ADMIN.
- R3 OQ-10: PUBLIC problems require an active class membership for students (code brought in line with REQ-PROB-003).
- R4 OQ-01 exam: one ACTIVE exam session per participation and problem (resume).
- R5 OQ-01 practice / OQ-13: new session per open; stale practice sessions (24 h without activity) → ABANDONED.
- R6 OQ-13: server contract as built; client contract for the frontend.
- R7 OQ-04, 06, 07, 08, 09, 11, 15, 23: current behaviour confirmed (OQ-23 error code renamed to EXAM_ONGOING_CANCEL_FORBIDDEN).
- R8 OQ-03: OUT_OF_SCOPE V1. R9 OQ-12: publication = assignment, no due date. R10 OQ-24: read-only reuse.

Consequence:
No OPEN question remains. R1–R5 and the R7 rename are implemented as Phase 15A.

---

## Decision: Phase 15A Lock

Date:
2026-10-29

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-29): "Lock + push".

Locked Baseline:
| Phase | Spec | Lock commit | Tag | Verification |
|---|---|---|---|---|
| 15A Open-question review fixes | docs/41 | this commit | `phase-15a-oq-review-locked` | 536 + 8 passed (Phase 03–15A), compose E2E 4 |

Pushed to origin with `main` fast-forwarded to this commit.

---

## Decision: Phase 16 CI & Branch Protection Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all". All recommendations D1–D6 in `docs/42_CI_AND_BRANCH_PROTECTION.md` §6 are approved without overrides.

Approved Decisions (summary):
D1 GitHub Actions on GitHub-hosted runners; D2 six regression groups in parallel on every push and PR; D3 compose E2E on pushes to `main`, nightly and on demand; D4 `main` protection: PR required, `ci` check required and up to date, no force push or deletion, applies to admins, 0 required approvals; D5 the owner installs and authenticates `gh`, then PRs and protection are handled through it; D6 tech-debt fixes (duplicate `Settings`, Pydantic `class Config`) included.

---

## Decision: Phase 16 Lock

Date:
2026-10-29

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-29): "Lock Phase 16".

Locked Baseline:
| Phase | Spec | Merged via | Tag | Verification |
|---|---|---|---|---|
| 16 CI & branch protection | docs/42 | PR #1 (`e5178bf`), PR #2 (record + this lock commit) | `phase-16-ci-locked` on the merge commit of PR #2 | local `regression.sh all` 538 passed; GitHub Actions all groups + compose E2E green on `main`; direct push to `main` rejected |

Correction:
The Phase 15A baseline is 536 passed (the "536 + 8" in the Phase 15A lock entry counted the re-run file twice); see docs/42 §7.3.

First phase locked under branch protection: the lock commit reached `main` through a pull request with `ci` green.

---

## Decision: Phase 17 Observability Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve both" (reply to "Approve all recommendations in both specs?", covering `docs/43_OBSERVABILITY.md` and the Phase 18 spec). All recommendations D1–D7 in `docs/43_OBSERVABILITY.md` §6 are approved without overrides.

Approved Decisions (summary):
D1 `prometheus_client`, Prometheus text exposition; D2 every docs/07 §4 metric that maps to an existing code path plus HTTP and daemon-cycle metrics, the rest deferred as follow-ups; D3 each process (API and four daemons) serves its own registry; D4 `/health` liveness without checks and `/ready` readiness (PostgreSQL, Redis, storage), root path, no auth, 503 `NOT_READY` per rule #29; D5 metrics on an internal port `METRICS_PORT` (9100), never on the public API port, no auth; D6 JSON log lines via stdlib `logging` with `request_id` from a contextvar, request-id validation, generic 500 handler; D7 never-log list, redaction filter, automated marker test.

---

## Decision: Phase 17 Lock

Date:
2026-10-29

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-29): "Merge when green" (PR #3), then "Lock Phase 17".

Locked Baseline:
| Phase | Spec | Merged via | Tag | Verification |
|---|---|---|---|---|
| 17 Observability | docs/43 | PR #3 (`e00e42b`), lock PR (this commit) | `phase-17-observability-locked` on the merge commit of the lock PR | `test_phase17_observability.py` 23 passed; isolated local groups signals/observation/phase10plus 297 passed; GitHub Actions all 6 groups green on PR #3 and compose E2E green on `phase17` (probes, port 9100 in all five containers) |

Note:
Groups auth/academic/judge were verified on CI only: seven older test files hard-code `localhost:5432`, so a local run cannot keep them off the shared container (docs/43 §7.3, follow-up §7.4).

---

## Decision: Phase 18 Backup & Restore Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve both" (reply to "Approve all recommendations in both specs?", covering docs/43 Phase 17 and docs/44 Phase 18). All recommendations D1–D7 in `docs/44_BACKUP_AND_RESTORE.md` §7 are approved without overrides.

Approved Decisions (summary):
D1 daily logical `pg_dump --format=custom` (WAL/PITR is the upgrade path); D2 daily at 19:00 UTC, configurable `BACKUP_TIME_UTC`, plus manual runs; D3 key list and dump from one exported snapshot, copy only referenced blobs with hash check, a missing blob fails the backup; D4 `backup` service in `docker-compose.yml`; D5 self-contained set per backup in `${BACKUP_DIR:-./backups}`, keep newest 14, effective retention 180 + 14 days documented; D6 restore drill script run now and as a nightly/on-demand CI job (not a required check); D7 no tool-level encryption in V1, `0700` directory, runbook requires an encrypted off-host copy.

---

## Decision: Phase 18 Lock

Date:
2026-10-29

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-29): "Merge when green" (PR #5), then "Lock Phase 18".

Locked Baseline:
| Phase | Spec | Merged via | Tag | Verification |
|---|---|---|---|---|
| 18 Backup & restore | docs/44 | PR #5 (`bad0dc9`), lock PR (this commit) | `phase-18-backup-locked` on the merge commit of the lock PR | restore drill passed on this machine (restore 22 s, 20 s after merging Phase 17; RTO 4 h) and on GitHub (`backup-drill`); scheduled backup and pruning checked; local `regression.sh all` on a disposable PostgreSQL 580 passed, 0 failed (557 before merging Phase 17); GitHub Actions all 6 groups green on PR #5 |

Note:
The local regression now honours `PG_BASE` for every test file (docs/44 §8.2), so all groups, auth/academic/judge included, can be verified locally off the shared container. This closes the follow-up recorded in the Phase 17 lock entry.

---

## Decision: Phase 19 Retention Purge Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all" (reply to "Approve all recommendations D1–D9 in docs/45?"). All recommendations D1–D9 in `docs/45_RETENTION_PURGE.md` §6 are approved without overrides.

Approved Decisions (summary):
D1 purge raw trace only (trace events, scratchpad revisions, checkpoint snapshots no run/submission/final code references, and their blobs) after `retention_days`, plus refresh tokens expired more than 7 days; academic records and audit logs kept; D2 hard delete, session row kept with `trace_purged_at`; D3 one service used by a CLI (`retention-purge`, dry run by default, `--apply`) and a reconciler hook off by default (`RETENTION_PURGE_ENABLED=false`), daily, bounded batches, `SKIP LOCKED` + advisory lock; D4 exclusions of docs/45 §3.1 plus `exams.retention_hold` set by ADMIN via `PUT /api/v1/admin/exams/{id}/retention-hold` (audited); D5 one `RETENTION_PURGE` audit row per applied batch; D6 rows deleted and committed before blobs, only unreferenced blobs deleted, failures left to the orphan sweep; D7 reuse admin `retention_days`, unset default 30 → 180, floor `RETENTION_MIN_DAYS=30`; D8 purge metrics in `app/core/metrics.py`; D9 merge only after Phase 18 is locked on `main`.

---

## Decision: Phase 19 Lock

Date:
2026-10-29

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-29): "Merge when green" (PR #7), then "Lock Phase 19".

Locked Baseline:
| Phase | Spec | Merged via | Tag | Verification |
|---|---|---|---|---|
| 19 Retention purge | docs/45 | PR #7 (`32123f0`), lock PR (this commit) | `phase-19-retention-locked` on the merge commit of the lock PR | `test_phase19_retention.py` 13 passed; migration `c3e7a1f5d920` up/down/up; local `regression.sh all` on a disposable PostgreSQL after merging Phase 18: 593 passed, 0 failed (47 files); GitHub Actions all 6 groups green on PR #7 |

Note:
Merged after `phase-18-backup-locked` was on `main` (docs/45 D9). The daily purge hook ships disabled (`RETENTION_PURGE_ENABLED=false`); enabling it in a deployment is an operator step (RUNBOOK §10), after a backup.

---

## Decision: Roadmap after Phase 19 (frontend next, go-live gate G1)

Date:
2026-10-29

Status:
APPROVED_ROADMAP

Approval Source:
Project Owner explicit authorization (2026-10-29): "ok thực hiện 2 cái này trước: Đưa CORS hoặc reverse proxy vào spec của phase frontend. Đặt một mốc cứng: trước khi có người dùng thật đầu tiên, phải xong backup ra ngoài máy chủ và alert tối thiểu." This followed the recommendation to build the frontend next and defer the other operational tasks.

Decisions (recorded in `docs/ROADMAP.md`):
- The frontend is the next phase. Its specification must decide how the browser reaches the API: CORS with a configured origin list, a same-origin reverse proxy, or both. The backend has no CORS configuration today.
- Go-live gate G1 (hard): before the first real user, G1.1 an encrypted off-host backup copy with one verified restore from it, and G1.2 minimal alerting (backup failed or stale, daemon stale, `/ready` failing, judge backlog, disk usage). Each is done through its own locked phase. Until then deployments hold only test or demo data.
- Deferred, no fixed order: load test (after the frontend), compose `api` healthcheck, the docs/43 deferred metrics, dashboards, enabling the daily retention purge, trace partitioning, trace export and audit-log expiry.

---

## Decision: Phase 20A Frontend Foundation Specification Approval

Date:
2026-10-29

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-29): "Approve all" (reply to "Do you approve all 13 recommendations in docs/46 §6?"). All recommendations D1–D13 in `docs/46_FRONTEND_FOUNDATION.md` §6 are approved without overrides.

Approved Decisions (summary):
D1 React + TypeScript + Vite SPA in `apps/web` (supersedes "Next.js" in docs/07/10); D2 TanStack Query + React Router; D3 API client generated from `app.openapi()` with pinned `openapi-typescript` + `openapi-fetch`, generated files committed, CI fails when stale; D4 Mantine; D5 Monaco via `@monaco-editor/react`, bundled locally; D6 same origin (Vite dev proxy, NGINX in production), no CORS, no backend change, no WebSocket `Origin` check in 20A (re-evaluated in 20B); D7 access token in memory, refresh token in `localStorage`, cross-tab single-flight refresh via Web Locks, strict CSP; D8 pure TS trace module, persist-before-send in IndexedDB, batching, backoff, flush barrier before submit/end, single writer per session; D9 client event payload contract (one `EDITOR_CHANGED` per change with the docs/01 fields, no coalescing); D10 resume an ACTIVE practice session only when this browser holds its draft, otherwise end it and start a new one; D11 Vitest + backend contract test + `web` job folded into `ci`, Playwright in `web-e2e` with the compose-e2e cadence plus a recorded local run before lock; D12 Vietnamese UI, one strings file; D13 `apps/web` NGINX image and one new compose service `web`.

---

## Decision: Phase 20A Lock

Date:
2026-10-30

Status:
LOCKED

Approval Source:
Project Owner explicit authorization (2026-10-30): "Merge khi xanh" (reply to "Merge PR #10 bằng merge commit?", the option reading "Merge PR #10 bằng merge commit, rồi làm PR lock Phase 20A").

Locked Baseline:
| Phase | Spec | Merged via | Tag | Verification |
|---|---|---|---|---|
| 20A Frontend foundation and student practice | docs/46 | PR #10 (`b1a4f0f`), lock PR (this commit) | `phase-20a-frontend-foundation-locked` on the merge commit of the lock PR | Vitest 28 passed; `test_phase20a_trace_contract.py` 2 passed; local `regression.sh all` on a disposable PostgreSQL: 595 passed, 0 failed (48 files); Playwright 4 passed locally (separate compose project) and in CI (`compose E2E`, run 40996813410 on `main`); GitHub Actions all groups and `web` green on PR #10 |

Note:
No backend application code or migration changed. Deferred follow-ups (docs/46 §3.10, §7.2): server-side validation of `EDITOR_CHANGED` payloads, a student endpoint returning the latest own snapshot (resume on another device), httpOnly-cookie auth, the WebSocket `Origin` decision (20B), slimming the Monaco bundle. Go-live gate G1 (ROADMAP §3) still applies: test or demo data only. The running demo stack has no `web` service until it is rebuilt.

---

## Decision: Phase 20B Teacher Observation UI Specification Approval

Date:
2026-10-30

Status:
APPROVED_SPECIFICATION

Approval Source:
Project Owner explicit authorization (2026-10-30): "Duyệt tất cả" (reply to "Bạn duyệt cả 9 khuyến nghị trong docs/47 §6?"). All recommendations D1–D9 in `docs/47_TEACHER_OBSERVATION_UI.md` §6 are approved without overrides.

Approved Decisions (summary):
D1 scope = teacher observation screens plus minimal class management (create class, invite code) and student join-by-code; problem authoring deferred to its own phase; D2 additive backend change: `MemberResponse` gains `username`, `full_name` (no migration); D3 client replay engine (all events, diffs from empty, memoised seek, stop at gaps, verify against every snapshot, rebase on mismatch); D4 teacher WebSocket per tab with query invalidation, token-refresh reconnect, backoff and REST resync, plus 15 s refresh of an open ACTIVE session; D5 no WebSocket `Origin` check (bearer token in first message, no cookies); D6 neutral Vietnamese signal labels, evidence table with timeline links, forbidden-word test; D7 practice page shows statement and editor only after the session starts (`FAST_FIRST_CODE` baseline); D8 annotations on the session page and listed on the student page; D9 Vitest + one backend test + 3 Playwright tests in the existing `compose-e2e` step.

---

## Decision: Phase 20B Amendment D10 (refresh-token reuse grace)

Date:
2026-10-30

Status:
APPROVED_SPECIFICATION_AMENDMENT

Approval Source:
Project Owner explicit choice (2026-10-30) between three options for the logout-on-reload defect found by CI after PR #12: "Backend: cho phép trễ 10 giây (Recommended)".

Context:
Phase 20B (PR #12, merged as `930e809`) is merged but not locked: the first CI run of the teacher Playwright tests on `main` failed twice (runs 41003368446, 41006123496). The logs show a page reload during `POST /auth/refresh` losing the rotated token, after which reuse detection revoked the family (docs/47 F12).

Approved Decision:
docs/47 D10 (a): `refresh_sessions.rotated_at` (migration); a token rotated less than `REFRESH_REUSE_GRACE_SECONDS` (default 10) ago whose family still has an active token is accepted once more and yields new tokens in the same family; every other reuse still revokes the family. Logout, logout-all and password change stay final. The Phase 20B lock waits for this fix and a green compose E2E on `main`.
