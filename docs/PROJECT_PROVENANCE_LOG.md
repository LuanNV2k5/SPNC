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
