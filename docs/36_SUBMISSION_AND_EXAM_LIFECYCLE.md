# 36 — SUBMISSION, JUDGING & EXAM LIFECYCLE (PHASE 10) SPECIFICATION

> **Module:** Test Cases, Submission Judging, Exam Lifecycle & Results (Phase 10)
> **Status:** APPROVED 2026-10-28 (all §9 recommendations; see PROJECT_PROVENANCE_LOG.md) — IMPLEMENTATION IN PROGRESS
> **Date:** 2026-10-28
> **Parent Baseline:** `phase-09-observation-locked` (`e0b3315`)
> **Proposed Branch:** `phase10`
> **Target Lock Tag:** `phase-10-submission-locked`

---

## 1. Purpose

The system can run student code (Phase 07) and observe how it was written (Phases 06–09). It still **cannot grade a submission or run an exam end-to-end**. Phase 10 closes the remaining MUST requirements of the core learning loop:

| Requirement | Summary | Current state |
|---|---|---|
| **REQ-PROB-002** (MUST) | Teacher adds test cases (input, expected_output, is_sample, score_weight); samples visible to students | `ProblemTestCase` model exists; **no API** |
| **REQ-RUN-004** (MUST) | Judge a submission against hidden test cases; verdict + per-testcase result | **Missing**: only single-input Runs are executed |
| **REQ-TRACE-012** (MUST) | Submit creates a SUBMIT snapshot + `SUBMISSION_MADE` trace event (snapshot_id, submission_id) | **Missing**: no submit endpoint |
| **REQ-EXAM-001..003** (MUST) | DRAFT → publish → SCHEDULED; automatic ONGOING at start and ENDED at end (≤ 60 s) | **Missing**: exam status never changes |
| **REQ-SESSION-003/004** (MUST) | On exam end: active sessions ENDED (`SYSTEM_EXAM_TIMEOUT`); auto-submit from the latest server-received snapshot; never fabricate code | **Missing** (deferred by 08E D8) |
| **REQ-EXAM-009** (MUST) | Participation: NOT_STARTED / IN_PROGRESS / COMPLETED / EXPIRED / CANCELLED | Code enum differs (`ABANDONED`, no EXPIRED/CANCELLED) |
| **REQ-EXAM-007** (MUST), REQ-STU-002 (SHOULD), OQ-15 | Results visible to students only per `allow_view_result_after` | Flag missing on `Exam` |
| REQ-EXAM-010/011 (SHOULD) | Teacher cancels DRAFT/SCHEDULED exam with metadata + AuditLog; participations → CANCELLED | Teacher cancel missing (only an admin endpoint exists, see F6) |
| REQ-OBS-007 (SHOULD) | Class/exam statistics | Deferred by docs/35 D5 until submissions exist |
| REQ-STU-004 (SHOULD) | Points for ACCEPTED submissions | **Blocked by OQ-16** (excluded) |

---

## 2. Findings From the Current Code (2026-10-28)

| # | Finding | Location | Impact |
|---|---|---|---|
| F1 | No API for test cases. Problems cannot be graded. | `app/models/problem.py:ProblemTestCase` | REQ-PROB-002 |
| F2 | `Submission` has no `exam_id`, `judge_result`, `source`, or `execution_generation`/lease. `snapshot_id` is NOT NULL. | `app/models/run_submit.py` | schema migration |
| F3 | `Exam.status` never leaves `DRAFT`, so students can join a **DRAFT** exam whenever the time window is open. There is no publish step and no scheduler. | `app/services/academic.py:318-331` | REQ-EXAM-001..003, D10/D11 |
| F4 | Enum drift vs domain §1.5: `ExamStatus.COMPLETED` (domain `ENDED`), `ParticipationStatus.ABANDONED` (domain has `EXPIRED`, `CANCELLED`). `ExamParticipation` lacks `expired_at`. `Exam` lacks `allow_view_result_after`, `cancelled_at/by/reason`. | `app/models/exam.py` | D8 |
| F5 | Adapters use global `JUDGE_*` limits; `Problem.time_limit_ms` / `memory_limit_mb` are ignored. | `app/services/judge/adapters.py` | D12 |
| F6 | `PATCH /admin/exams/{id}/cancel` cancels **ONGOING** exams, but OQ-23's current assumption and NG12 say ADMIN does not cancel ONGOING in V1. | `app/api/endpoints/admin.py:71` | D13 |
| F7 | No student "finalize exam" action, so `COMPLETED` is unreachable. | — | §4 10B |
| F8 | Domain §1.6 says a timeout submission may be created with `code_snapshot_id = null`. UC-E02 A3 and REQ-SESSION-004 say **no** submission when there is no snapshot. | docs conflict | D1 |

---

## 3. Judging Model

- A **Submission** references one immutable `CodeSnapshot` (reason `SUBMIT`, or the latest snapshot on timeout).
- The worker consumes `{"kind": "submission", "submission_id": ...}` from the existing Redis queue. Runs keep `{"run_id": ...}`.
- The worker reuses the Phase 07 fencing (PENDING → RUNNING CAS, `execution_generation`, lease, stale-result rejection) and the reconciler sweep.
- Each test case runs in the existing sandbox using the problem's `time_limit_ms` / `memory_limit_mb` (D12), in `order_index` order.
- Per-testcase result: `{testcase_id, order_index, is_sample, verdict, passed, execution_time_ms, memory_used_kb}`. `stdout`/`stderr` are stored **only for sample** test cases (D7).
- Output comparison per D3. Verdict aggregation and score per D4.

---

## 4. Scope by Sub-phase

### 10A — Test cases, submit, judge
| Item | Detail |
|---|---|
| Test case CRUD | `POST/GET/PATCH/DELETE /api/v1/problems/{id}/test-cases[/{tc_id}]`, owner TEACHER only. `is_sample` maps to `NOT is_hidden`. Editing is blocked while the problem is in an ONGOING exam (409). |
| Student sample view | `GET /api/v1/problems/{id}/samples`: students with problem access see `is_sample` cases only. Hidden cases are never returned. |
| Submit | `POST /api/v1/my/coding-sessions/{id}/submissions {snapshot_id}`. The snapshot must belong to the session. Session ACTIVE. Exam context requires participation IN_PROGRESS and the time window open (DI-8, REQ-EXAM-012). Creates the `Submission` (PENDING, `source=STUDENT`, `exam_id` set for exam sessions) and appends a server-authored `SUBMISSION_CREATED` trace event `{source:"SERVER", submission_id, code_snapshot_id}` (REQ-TRACE-012). Then finalizes the session per D2. All in one transaction, then enqueue. |
| Judge worker | Submission jobs as in §3. Writes `verdict`, `score`, `judge_result`, `status`. Exam: recompute `ExamParticipation.total_score` (D5). |
| Read | `GET /api/v1/my/submissions[/{id}]` (exists) gains `judge_result` filtered per D7 and the result-visibility rule D14. Teachers see full results through the observation API (session timeline already links submissions). |
| Realtime | NOTIFY `submission.judged {submission_id, session_id, student_id, verdict}` on the docs/35 channel. |

### 10B — Exam lifecycle & timeout finalization
| Item | Detail |
|---|---|
| Enum/schema alignment (D8) | `ExamStatus`: DRAFT / SCHEDULED / ONGOING / ENDED / CANCELLED. `ParticipationStatus`: NOT_STARTED / IN_PROGRESS / COMPLETED / EXPIRED / CANCELLED. Adds `exam_participations.expired_at`, `exams.allow_view_result_after` (default false), `cancelled_at/by/reason`. |
| Publish | `POST /api/v1/exams/{id}/publish`: owner; DRAFT → SCHEDULED. Requires `start_time > now`, ≥1 assigned class, ≥1 problem, and every problem has ≥1 test case (OQ-09 assumption: validate at publish). |
| Student access (D11) | Join/start requires status ∈ {SCHEDULED, ONGOING} **and** the time window (REQ-EXAM-012 stays authoritative). DRAFT/CANCELLED → 403. |
| Exam scheduler daemon | `app/exam_scheduler.py` (D10), 30 s tick, idempotent, row-locked. SCHEDULED → ONGOING at `start_time`. ONGOING → ENDED at `end_time`, which triggers the **timeout finalization** for each IN_PROGRESS participation: (1) every ACTIVE exam session → `session_lifecycle.finalize_session(..., SYSTEM_EXAM_TIMEOUT)` (Phase 08E); (2) for each such session with a server-received snapshot newer than its last submission → auto-submit (`source=SYSTEM_EXAM_TIMEOUT`); no snapshot → no submission (D1); (3) participation → EXPIRED, `expired_at=now`. Crash-safe: re-running a tick finishes partial work without duplicates. |
| Finalize | `POST /api/v1/my/exams/{id}/finalize`: student; IN_PROGRESS → COMPLETED (`completed_at`). Ends that student's ACTIVE exam sessions (actor STUDENT). No auto-submit, because the student chose to finish. |
| Teacher cancel | `POST /api/v1/exams/{id}/cancel {reason}`: owner; DRAFT/SCHEDULED only; metadata + AuditLog `EXAM_CANCELLED`; NOT_STARTED/IN_PROGRESS participations → CANCELLED; no submissions created (REQ-EXAM-011). |
| Admin cancel (D13) | `PATCH /admin/exams/{id}/cancel` restricted to DRAFT/SCHEDULED until OQ-23 is decided (ONGOING → 409 `EXAM_ONGOING_CANCEL_UNDECIDED`). |
| Result visibility (D14) | Practice: own results always. Exam: own results only when status ENDED **and** `allow_view_result_after = true`. Otherwise verdict/score/judge_result are hidden (submission existence still listed). |
| Observation | docs/35 D6 derivation becomes stored state. `get_exam_observation` reads the real enum. |

### 10C — Statistics (REQ-OBS-007, SHOULD)
`GET /api/v1/classes/{id}/statistics` and `GET /api/v1/exams/{id}/statistics` (owner):
- average score and score distribution (10 buckets);
- ACCEPTED vs non-ACCEPTED ratio;
- average `working_time_seconds` (Phase 08E);
- per-student: score, run count, submission count, session count.

Computed from Submission/Run/Session data only, with no judgment labels. Uses the docs/35 §3 visibility rule.

### 4.1 Out of Scope
- REQ-STU-004 points / gamification (OQ-16 open).
- OQ-23 decision itself (ADMIN cancel of ONGOING exams).
- Frontend; shared blob storage; WebSocket serving dependency (docs/35 §10.4).
- Plagiarism or any automated judgment (NG1, NG6).

---

## 5. Data Model Changes (new migrations only)
- `submissions`: `exam_id` (FK, nullable), `source` (`STUDENT` | `SYSTEM_EXAM_TIMEOUT`), `judge_result` JSONB, `execution_generation` INT default 0, `lease_expires_at` TIMESTAMPTZ. Indexes on `(exam_id, student_id, problem_id)`.
- `exams`: `allow_view_result_after` BOOL default false, `cancelled_at`, `cancelled_by` (FK users), `cancel_reason`.
- `exam_participations`: `expired_at`.
- Enum value migration (D8): `UPDATE exams SET status='ENDED' WHERE status='COMPLETED'`; `UPDATE exam_participations SET status='EXPIRED' WHERE status='ABANDONED'`. Both are expected to touch 0 rows, because neither value is written by current code.
- NOTIFY trigger for `submission.judged`.

---

## 6. Invariants
1. Submission references a server-received snapshot. Code is never fabricated (DTI-06, REQ-SESSION-004).
2. Exam submissions only while participation IN_PROGRESS and inside the time window (DI-8, REQ-EXAM-012). The timeout auto-submit is the sole SYSTEM exception, and it uses only snapshots received before `end_time`.
3. Hidden test case input/expected output never reaches students, in any endpoint or in `judge_result`.
4. Verdicts never create attention signals (domain §1.6).
5. Stale judge generations cannot overwrite results (Phase 07 CAS).
6. Exam transitions are idempotent and server-side; authorization never depends on scheduler lag (REQ-EXAM-012).

---

## 7. Acceptance Criteria

| ID | Criterion |
|---|---|
| AC-10-01 | Test case CRUD owner-only. Students see samples only; hidden data absent from every student response. |
| AC-10-02 | Submit creates Submission + `SUBMISSION_CREATED` server event with snapshot/submission ids; session handled per D2; cross-session snapshot → 403; inactive session → 403. |
| AC-10-03 | Judge: all-pass → ACCEPTED with full score; WA/TLE/RE/CE per D4 precedence; per-testcase results; partial score per D4; problem limits applied (D12). |
| AC-10-04 | Duplicate queue delivery / stale generation cannot double-write; reconciler recovers stuck PENDING/RUNNING submissions. |
| AC-10-05 | Publish validation errors (no class / no problem / problem without test cases / past start) → 422. DRAFT exam cannot be joined. |
| AC-10-06 | Scheduler moves SCHEDULED→ONGOING→ENDED within one tick after the boundary. Running a tick twice is a no-op. |
| AC-10-07 | Timeout: ACTIVE exam sessions → ENDED `SYSTEM_EXAM_TIMEOUT` with `SESSION_ENDED`; auto-submission only where a snapshot exists and is newer than the last submission; none otherwise; participations → EXPIRED with `expired_at`. |
| AC-10-08 | Finalize → COMPLETED; later submits → 403. |
| AC-10-09 | Teacher cancel rules + AuditLog + participations CANCELLED + no submissions. Admin cancel of ONGOING → 409. |
| AC-10-10 | Result visibility per D14 (practice always; exam only ENDED + flag). |
| AC-10-11 | `total_score` per D5. Statistics endpoints owner-only and numerically correct on a fixture. |
| AC-10-12 | Full Phase 03–09 regression passes on fresh databases; scope fence (no points, no UI). |

---

## 8. Implementation Plan (files)

| Step | Files |
|---|---|
| 10A | migration `phase10a_submission_judging`. `app/services/testcase.py`, `app/services/submission.py`, repositories/schemas/endpoints. `app/services/judge/grader.py` (comparison + aggregation). `worker.py` / `reconciler.py` / `queue.py` extended. Tests `test_testcases.py`, `test_submissions.py`, `tests/judge/test_grader.py`, `test_submission_fencing.py`. |
| 10B | migration `phase10b_exam_lifecycle`. `app/services/exam_lifecycle.py`, `app/exam_scheduler.py`. Academic service/endpoints (publish, finalize, cancel, access rule). Admin cancel restriction. Tests `test_exam_lifecycle.py`, `test_exam_timeout.py`. |
| 10C | `app/services/statistics.py` + endpoints. Test `test_statistics.py`. |

---

## 9. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | Timeout with no snapshot (F8) | (a) no Submission (UC-E02 A3, REQ-SESSION-004), and amend domain §1.6 via DCR; (b) Submission with null snapshot (domain §1.6) | **(a)**. Two authoritative sources agree, and a null-code submission cannot be judged. |
| **D2** | Does submit end the session? | (a) yes, per UC-E02 11e-f: session ENDED (actor STUDENT); further attempts open a new session; (b) session stays ACTIVE, multiple submits per session | **(a)**. Follows the use case and keeps one final snapshot per session (aligns with 08E `final_loc`). |
| **D3** | Output comparison | (a) normalize CRLF→LF, strip trailing whitespace per line and trailing empty lines, then exact match; (b) byte-exact; (c) token-based | **(a)**. Tolerant of invisible differences, strict on content. |
| **D4** | Verdict & score | Verdict: COMPILE_ERROR if compilation fails (no further cases); else the verdict of the first failing case by `order_index`; else ACCEPTED. Score: `max_score × passed_weight / total_weight`, rounded down (practice: base 100). | **As stated**. All cases still run after a failure, for per-testcase detail. |
| **D5** | Exam `total_score` per problem | (a) best submission; (b) latest submission | **(a) best**. Exploring is never penalized. Teachers still see every submission. |
| **D6** | Re-judge when test cases change | (a) no automatic re-judge in V1; (b) re-judge all | **(a)**. Results reflect the test cases at judge time, recorded in `judge_result`. |
| **D7** | What students see in `judge_result` | (a) per-case verdict/time/memory for all cases; input/expected/stdout only for samples; (b) totals only | **(a)**. Matches UC-G01 "per-testcase nếu cho phép" without leaking hidden data. |
| **D8** | Enum alignment (F4) | (a) align to domain (`ENDED`, `EXPIRED`, `CANCELLED`; drop `COMPLETED` exam / `ABANDONED` participation); (b) keep code values | **(a)**. Domain is authoritative. Data migration is expected to touch 0 rows. |
| **D9** | Submission rate limit | (a) none in V1; (b) min interval per session | **(a)**. D2 already limits it to one submit per session. |
| **D10** | Exam scheduler placement | (a) separate daemon `exam_scheduler.py` (30 s tick); (b) inside signal scheduler | **(a)**. Failure isolation; meets the ≤ 60 s requirement. |
| **D11** | Student exam access | (a) status ∈ {SCHEDULED, ONGOING} **and** time window; (b) time window only (current) | **(a)**. Closes F3 (DRAFT exams joinable) while keeping REQ-EXAM-012. |
| **D12** | Judge limits | (a) per-problem `time_limit_ms` / `memory_limit_mb`, capped by global `JUDGE_*` maxima; (b) global only | **(a)**. Uses the stored problem settings safely. |
| **D13** | Admin cancel of ONGOING (F6) | (a) restrict to DRAFT/SCHEDULED until OQ-23 is decided; (b) leave as is | **(a)**. Aligns code with OQ-23's current assumption and NG12. Changes Phase 04 behaviour. |
| **D14** | Student result visibility (OQ-15 current assumption) | (a) practice always; exam only after ENDED + `allow_view_result_after`; (b) always visible | **(a)**. REQ-EXAM-007 + OQ-15 assumption. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before implementation, with a DCR for D1 (domain §1.6 amendment) and D13. Order: 10A → 10B → 10C, each verified before the next (PROJECT_RULES #3).

---

## 10. Verification Record

*To be completed at Phase 10 closure.*
