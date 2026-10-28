# 38 — MUST REQUIREMENT GAP CLOSURE (PHASE 12) SPECIFICATION

> **Module:** Class invite codes, problem bank completeness and locks, exam edit lock and per-student duration, post-deadline ingest cutoff, run/first-code trace facts (Phase 12)
> **Status:** APPROVED 2026-10-29 (all §7 recommendations; see PROJECT_PROVENANCE_LOG.md) — 12A/12B/12C IMPLEMENTED AND VERIFIED 2026-10-29 (§8); lock tag pending Project Owner review
> **Date:** 2026-10-29
> **Parent Baseline:** `phase11` @ `dfa16c6` (Phases 10 and 11 implemented, locks pending)
> **Proposed Branch:** `phase12`
> **Target Lock Tag:** `phase-12-must-gaps-locked`

---

## 1. Purpose

A review of `03_REQUIREMENTS.md` against the code (2026-10-29) found MUST requirements that no phase has implemented. Each is listed in §2 with its evidence. Phase 12 closes them without adding new features. Two of them (REQ-TRACE-002, REQ-TRACE-011) cannot be met literally without breaking the client-owned sequence numbering, so §7 asks for a decision and a DCR.

Out of scope: REQ-USER-007 (SHOULD, admin-configurable idle threshold), REQ-TRACE-013 (SHOULD, periodic checkpoints), REQ-STU-004 (OQ-16), frontend, OQ-26.

---

## 2. Findings

| # | Requirement (MUST) | Current code | Gap |
|---|---|---|---|
| G1 | REQ-CLASS-001/005: class has a unique `invite_code`; STUDENT joins with it (UC-B03: class ACTIVE, STUDENT ACTIVE, already enrolled → message) | `Class` has no `invite_code`; only the teacher enrolls by `student_id` | Missing |
| G2 | REQ-PROB-001: problem has `constraints`, `input_format`, `output_format` (domain §1 also lists `difficulty`) | `Problem` has title, description, limits, visibility, languages | Missing fields |
| G3 | REQ-PROB-006: problem bank filter by difficulty / language / visibility | `GET /problems` paginates only | Missing filters |
| G4 | REQ-PROB-004: problem not editable while in an exam SCHEDULED/ONGOING; editable when DRAFT/ENDED/CANCELLED | `PATCH /problems/{id}` has no exam check. Test-case edits are blocked only while ONGOING (Phase 10A). | Missing / partial |
| G5 | REQ-PROB-005: problem cannot be deleted while in an exam SCHEDULED/ONGOING | No delete endpoint. Sessions/submissions reference problems with `ON DELETE RESTRICT`. | Missing |
| G6 | REQ-EXAM-006: exam not editable when ONGOING; "chỉ cho sửa khi DRAFT" | `PATCH /exams/{id}`, attach/detach problem, assign/unassign class accept any status | Missing |
| G7 | REQ-EXAM-001: exam has `duration_minutes` | No column. Semantics are not defined in docs 01/02/03. | Missing + undefined (§7 D7) |
| G8 | REQ-EXAM-012 / REQ-TRACE-006 (deadline enforced server-side): after `end_time` an exam session still accepts trace events, snapshots, runs and scratchpad writes until the scheduler finalizes it | docs/36 §10.9 | Missing cutoff |
| G9 | REQ-TRACE-011: a Run records `RUN_EXECUTED` with `code_snapshot_id, input_used, output, result, error_message, execution_time_ms` | The Run row holds all of these; no server trace event; the teacher timeline does not show runs | Partial (§7 D9) |
| G10 | REQ-TRACE-002: `FIRST_CODE_INPUT` recorded once per session | No such event; `coding_sessions.first_code_at` exists but is never set (FAST_FIRST_CODE derives it from the first `EDITOR_CHANGED`) | Missing (§7 D10) |
| G11 | REQ-TRACE-012 / docs/36 §10.9: `SUBMISSION_CREATED` is server-authored, yet clients can still ingest it | `ingest_trace_batch` reserves only `SESSION_ENDED` | Integrity gap (§7 D11) |

Server-authored events can only be appended when the client stops writing (submit, end). While a session is open the client owns `sequence_number`, so a server event at `max+1` would collide with the client's next event (unique `(session_id, sequence_number)`). This is why D9/D10 avoid mid-session server events.

---

## 3. Scope by Sub-phase

### 12A — Classes and problem bank
| Item | Detail |
|---|---|
| Invite code (G1) | `classes.invite_code` UNIQUE NOT NULL, generated server-side (D1), backfilled for existing classes by the migration. Shown to the owner in class responses; never to students. `POST /api/v1/classes/{id}/invite-code/rotate` (owner) replaces it (D2). |
| Join (G1) | `POST /api/v1/my/classes/join {invite_code}` (STUDENT, ACTIVE): unknown code → 404 `INVITE_CODE_INVALID`; class inactive → 403 `CLASS_NOT_ACTIVE`; already an active member → 409 `ALREADY_ENROLLED`; previously removed member → membership re-activated (D3); else new active membership. Enrollment is auto-approved (OQ-08 current assumption). |
| Problem fields (G2) | `constraints`, `input_format`, `output_format` (TEXT, optional) and `difficulty` (`EASY`/`MEDIUM`/`HARD`, optional) on create/update/response. |
| Filters (G3) | `GET /api/v1/problems?difficulty=&language=&visibility=` (owner's bank). Invalid values → 422. |
| Problem lock (G4) | Problem PATCH and every test-case create/update/delete → 409 `PROBLEM_IN_ACTIVE_EXAM` while the problem is attached to any exam in SCHEDULED or ONGOING (D4). Allowed for DRAFT/ENDED/CANCELLED. |
| Problem delete (G5) | `DELETE /api/v1/problems/{id}` (owner) per D5. 409 `PROBLEM_IN_ACTIVE_EXAM` while in a SCHEDULED/ONGOING exam. |

### 12B — Exams
| Item | Detail |
|---|---|
| Edit lock (G6) | PATCH exam, attach/detach problem, assign/unassign class → 409 `EXAM_NOT_EDITABLE` unless the exam is DRAFT. Sole exception: `allow_view_result_after` may change in any status except CANCELLED (D14 needs it after ENDED) (D6). |
| Duration (G7) | `exams.duration_minutes` per D7. |
| Ingest cutoff (G8) | For exam sessions, trace batch, snapshot create, run create and scratchpad save → 403 `EXAM_ENDED` once the server clock passes the participant's deadline (D7/D8). Practice sessions are unaffected. Session end and the timeout finalization are unaffected. |

### 12C — Trace facts
| Item | Detail |
|---|---|
| Run record (G9) | Per D9. |
| First code (G10) | Per D10. |
| Reserved types (G11) | Per D11. |

---

## 4. Data Model Changes (new migration only)
- `classes.invite_code` VARCHAR(16) UNIQUE NOT NULL (backfill, then NOT NULL).
- `problems.constraints`, `input_format`, `output_format` TEXT NULL; `difficulty` VARCHAR(10) NULL with CHECK.
- `problems.deleted_at` TIMESTAMPTZ NULL (D5 option a).
- `exams.duration_minutes` INT NULL, CHECK > 0 (D7).

---

## 5. Invariants
1. Invite codes are unique and never returned to students.
2. A problem attached to a SCHEDULED/ONGOING exam never changes (statement, limits, test cases) and is never deleted.
3. A non-DRAFT exam's schedule, problems and classes never change.
4. No client data is accepted for an exam session after the participant's deadline (server clock).
5. Trace `sequence_number` stays client-owned while a session is open; server-authored events are only appended at submit/end.
6. Deleting a problem never removes history (sessions, runs, submissions, trace).

---

## 6. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-12-01 | Every class has a unique invite code; owner sees it, students never do; rotation invalidates the old code. |
| AC-12-02 | Join: valid → active membership; unknown → 404; inactive class → 403; already member → 409; removed member re-joins; LOCKED student → 403. |
| AC-12-03 | Problem create/update/read carry the new fields; bank filters by difficulty, language, visibility. |
| AC-12-04 | Problem and test-case edits and problem delete → 409 while in a SCHEDULED/ONGOING exam; allowed for DRAFT/ENDED/CANCELLED. |
| AC-12-05 | Deleted problems per D5 disappear from banks, cannot start new sessions, and history stays readable. |
| AC-12-06 | Exam edits rejected outside DRAFT, except `allow_view_result_after` (not when CANCELLED). |
| AC-12-07 | Duration per D7 enforced in access, ingest cutoff and timeout finalization. |
| AC-12-08 | Exam-session trace/snapshot/run/scratchpad writes after the deadline → 403; practice unaffected. |
| AC-12-09 | Run facts per D9; first-code fact per D10; reserved types per D11. |
| AC-12-10 | Full Phase 03–11 regression passes on fresh databases. |

---

## 7. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | Invite code format | (a) 8 chars from an unambiguous alphabet (no 0/O/1/I/L), cryptographically random, retry on collision; (b) UUID | **(a)**. Easy to type; ~10^12 space. |
| **D2** | Can the owner rotate the code? | (a) yes, rotate endpoint; (b) no | **(a)**. Lets a leaked code be revoked. |
| **D3** | Removed member uses the code again | (a) re-activate the existing membership (history kept); (b) refuse | **(a)**. Same student, same record; teacher can remove again. |
| **D4** | Problem lock scope | (a) problem fields **and** test cases locked in SCHEDULED and ONGOING exams (extends Phase 10A's ONGOING-only test-case lock); (b) problem fields only | **(a)**. A published exam was validated against its test cases (docs/36 publish rule); changing them afterwards breaks that check. Changes Phase 10A behaviour. |
| **D5** | Problem delete | (a) soft delete (`deleted_at`): hidden from banks/practice lists, no new sessions or exam attachment, existing history intact; (b) hard delete only when never used, else 409 | **(a)**. History is evidence and FKs are RESTRICT. |
| **D6** | Exam edit lock | (a) DRAFT-only per REQ-EXAM-006 AC; `allow_view_result_after` editable in any status except CANCELLED; (b) also allow edits while SCHEDULED | **(a)**. Follows the AC; a teacher can still cancel a SCHEDULED exam and recreate it. |
| **D7** | Meaning of `duration_minutes` (not defined in docs 01–03) | (a) optional per-student limit: deadline = `min(participation.started_at + duration, end_time)`; null = no per-student limit; enforced by the access rule, the ingest cutoff and the timeout finalization (a participant past their deadline is finalized on the next scheduler tick, auto-submit rules unchanged); validated `duration ≤ end_time − start_time`; (b) store only, no enforcement, and open an OQ | **(a)**, recorded as OQ-27 current assumption. It is the usual meaning of an exam duration and reuses the Phase 10B machinery. |
| **D8** | Post-deadline ingest | (a) reject with 403 `EXAM_ENDED` (client data after the deadline is never stored); (b) accept and flag | **(a)**. Server clock authoritative (REQ-TRACE-006, REQ-EXAM-012). |
| **D9** | REQ-TRACE-011 `RUN_EXECUTED` | (a) DCR: the `Run` row is the RUN_EXECUTED record (it holds every required field and references the snapshot); the client's `RUN_REQUESTED` event stays the meaningful event; the teacher timeline gains a `runs` list (snapshot id, input, output, verdict, error, time); (b) server appends a trace event on run completion, which needs a separate server sequence space (schema change) because the session may still be open or already ended | **(a)**. Meets the AC's data without breaking sequence ownership or the "SESSION_ENDED is last" invariant. |
| **D10** | REQ-TRACE-002 `FIRST_CODE_INPUT` | (a) DCR: the server records `coding_sessions.first_code_at` (server clock) at the first ingested `EDITOR_CHANGED`, once; exposed in session and timeline responses; FAST_FIRST_CODE keeps its evidence; (b) server-authored event (same collision problem as D9 b) | **(a)**. "Once per session" is enforced by the column. |
| **D11** | Reserve `SUBMISSION_CREATED` from client ingest | (a) reserve it like `SESSION_ENDED` (422 `TRACE_EVENT_TYPE_RESERVED`); (b) leave open | **(a)**. Since Phase 10A only the server writes it; a client copy would be a fake submission marker. Changes Phase 06 ingest behaviour for that type. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md` with DCRs for D4 (Phase 10A behaviour), D9, D10 and D11 (Phase 06 behaviour), and OQ-27 for D7. Order: 12A → 12B → 12C, each verified before the next.

---

## 8. Verification Record

### 8.1 Changes (2026-10-29)
| Sub-phase | Commit | Files |
|---|---|---|
| Approval | `8ac2904` | PROJECT_PROVENANCE_LOG (spec approval; DCRs SPNC_PROBLEM_LOCK_SCOPE, SPNC_RUN_EXECUTED_RECORD, SPNC_FIRST_CODE_FACT, SPNC_RESERVED_SUBMISSION_EVENT), OPEN_QUESTIONS (OQ-27) |
| 12A | `b56f527` | migration `d7f3b1c2e845`; `models/class_org.py` (`invite_code`, generator), `models/problem.py` (statement fields, `difficulty`, `deleted_at`); `services/problem_guard.py`; academic service/repo/endpoints (join, rotate, filters, soft delete); `services/testcase.py` (lock via the guard) |
| 12B | `6aeae89` | migration `e8a4c2d5f901`; `exams.duration_minutes`; `services/exam_access.py` (`participant_deadline`, `assert_participant_open`, `assert_session_writable`); trace/run services (cutoff); academic service (edit lock, duration validation); `services/exam_lifecycle.py` (participant deadline in finalize/timeout, overdue sweep) |
| 12C | this commit | `services/trace.py` (reserved set, `first_code_at`), `repositories/trace.py` (`mark_first_code`), observation timeline `runs` + `first_code_at`, `SessionResponse.first_code_at` |

### 8.2 Behaviour Notes
- **Invite codes:** 8 characters from `23456789ABCDEFGHJKMNPQRSTUVWXYZ`; entry is case-insensitive. `ClassResponse` (owner endpoints) carries `invite_code`; `GET /my/classes` uses `StudentClassResponse` without it. Existing classes got codes in the migration. Errors: 404 `INVITE_CODE_INVALID`, 403 `CLASS_NOT_ACTIVE`, 409 `ALREADY_ENROLLED`.
- **Problem lock:** status-based (SCHEDULED/ONGOING), 409 `PROBLEM_IN_ACTIVE_EXAM` for problem PATCH/DELETE and every test-case write. Replaces Phase 10A's time-window check and `PROBLEM_IN_ONGOING_EXAM`.
- **Soft delete:** `DELETE /problems/{id}` → 204, sets `deleted_at`. Hidden from the owner bank and public bank; 404 for students and other teachers, for practice start, exam attach, class publication, problem PATCH and test-case writes. The owner can still read it (`deleted_at` in the response). Sessions, submissions and trace are untouched.
- **Exam edit lock:** non-DRAFT exams refuse PATCH (except a body with only `allow_view_result_after`), attach/detach problem and assign/unassign class with 409 `EXAM_NOT_EDITABLE`. `allow_view_result_after` alone is refused only for CANCELLED.
- **Duration:** `duration_minutes` > 0 and ≤ the window (422 `EXAM_DURATION_TOO_LONG`). The participant deadline applies to exam-session start, submit, finalize, trace batch, snapshot, run and scratchpad (403 `EXAM_ENDED`). The scheduler finalizes participants past their own deadline in ONGOING exams, using only snapshots received before that deadline.
- **Cutoff without duration:** the deadline is `end_time`; an exam session also refuses writes once the exam is ENDED or CANCELLED.
- **First code:** `coding_sessions.first_code_at` is set from the server clock when a batch first inserts an `EDITOR_CHANGED`, with a conditional update (only while NULL); retries do not move it. Exposed in session responses and the teacher timeline. Existing sessions keep NULL.
- **Runs in timeline:** `GET …/sessions/{id}/timeline` adds `runs` (all runs of the session, oldest first, same shape as the teacher run list).
- **Reserved types:** `SESSION_ENDED` and `SUBMISSION_CREATED` in a client batch → 422 `TRACE_EVENT_TYPE_RESERVED`, whole batch refused.

### 8.3 Earlier Tests Adjusted
- `test_testcases.py`: lock test rewritten for D4 (status-based, new error code, DRAFT/ENDED/CANCELLED editable).
- `test_academic.py` (14 tests): exams are marked SCHEDULED after class/problem setup, because D6 forbids setup changes once published.

### 8.4 Verification
| Check | Environment | Result |
|---|---|---|
| Migrations `d7f3b1c2e845`, `e8a4c2d5f901` | Empty DB with two pre-existing classes, PostgreSQL 16.15 | up / down / up OK; each class backfilled with a distinct valid code |
| 12A `test_phase12a_classes_problems.py` | Disposable PostgreSQL 16.15, `spnc_phase10_submission_test` | **8 passed** |
| 12B `test_phase12b_exams.py` | same | **6 passed** |
| 12C `test_phase12c_trace.py` | same | **3 passed** |
| Phase 03–11 suites (incl. MinIO adapter on a disposable MinIO) | Fresh per-phase DBs migrated to head; Redis; Docker sandbox | **482 passed** |
| **Total (AC-12-10)** | each file run on its own | **499 passed, 0 failed** |
| Demo compose stack rebuilt from `phase12` on its existing volumes | Docker Desktop (Windows host) | `migrate` applied `d7f3b1c2e845`, `e8a4c2d5f901` to the demo DB; `tests/e2e/test_compose_stack.py` **4 passed**; live check: class shows `invite_code`, student joins with the lower-case code (201), `/my/classes` hides the code, `difficulty=EASY` filter, problem delete → 204 and hidden from the bank |

### 8.5 Known Limitations
- The two new migrations were also verified up/down/up on an empty database.
- REQ-USER-007, REQ-TRACE-013 (SHOULD) and REQ-STU-004 (OQ-16) remain out of scope. OQ-27 records the `duration_minutes` assumption.
