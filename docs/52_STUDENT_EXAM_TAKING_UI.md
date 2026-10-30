# Phase 21B — Student exam-taking UI

> **Status:** LOCKED — `phase-21b-student-exam-taking-ui-locked`
> **Date:** 2026-10-31
> **Approval:** Project Owner explicit authorization: “ok tiếp” (2026-10-31), approving decisions D1–D8 below.
> **Parent baseline:** `phase-21a-teacher-exam-ui-locked` (`de09220`)
> **Merged:** PR #18 (`4955ec5`)
> **Scope intent:** functional UI wired to the existing exam/session APIs; no visual-polish pass.

## 1. Context and gap

Phase 21A gives teachers a UI to configure, publish and observe exams. The web client has no student exam-taking route yet. Existing APIs cover exam listing, participation, exam coding sessions, trace persistence, runs, submissions and finalization. The API does not currently expose the ordered problem list and student-safe problem content for a particular exam, so the student client cannot discover which exam problems to open without a small additive endpoint.

The approved roadmap requires a specification and Project Owner approval before implementation. It does not order the remaining exam-taking and admin/statistics UI work. This phase selects student exam-taking because it completes the student side of the teacher exam workflow.

## 2. Recommended scope

- List exams assigned to the signed-in student, with scheduled/ongoing/ended/cancelled state and their time window.
- Show an exam summary and current participation state.
- Let an assigned student start or resume participation while the backend permits it.
- Show the exam's ordered problems, maximum score and student-visible statement/sample data after participation starts.
- Reuse the current coding workspace for exam sessions, including trace persistence, run, submit and judged-result visibility.
- Show the per-student deadline as an informational timer and let the student explicitly finalize participation.
- Present completed, expired and cancelled participation in a read-only state with only results the API marks visible.
- Support desktop and mobile interaction; this is functional responsive work, not visual polish.

No database migration is expected. Teacher exam management, admin screens and statistics remain out of scope.

## 3. Routes and API integration

| Route | Purpose |
|---|---|
| `/student/exams` | List exams assigned to the current student |
| `/student/exams/{examId}` | View status, start/resume participation, and enter an exam problem |
| `/student/exams/{examId}/problems/{problemId}` | Work on one exam problem in the existing workspace |

Existing endpoints to consume:

- `GET /api/v1/my/exams`
- `POST /api/v1/my/exams/{exam_id}/start`
- `GET /api/v1/my/exams/{exam_id}/participation`
- `POST /api/v1/my/exams/{exam_id}/finalize`
- `POST /api/v1/my/exam-sessions?participation_id=...`
- `GET/POST /api/v1/my/coding-sessions/{session_id}/...` for session state, traces, snapshots, runs and submissions
- `GET /api/v1/my/submissions` and `GET /api/v1/my/submissions/{submission_id}`

Proposed additive endpoint:

`GET /api/v1/my/exams/{exam_id}/problems`

It returns exam problems in `order_index` order with each problem's id, title, statement fields, constraints, input/output format, supported languages, limits, maximum score and public sample cases. It is student-scoped: the caller must be assigned to the exam and have an `IN_PROGRESS` participation. Hidden test cases and teacher-only metadata are never returned. The backend remains authoritative for exam access and deadline enforcement.

## 4. Approved decisions

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Student-visible exam problems | Add the scoped endpoint above; return only ordered problem content and public samples. Do not expose hidden tests. |
| D2 | When problem content becomes available | Require an assigned student with `IN_PROGRESS` participation. The list page may show an upcoming exam summary before its start time, but no problem content. |
| D3 | Session behaviour | Reuse the existing exam-session start endpoint, which resumes the active session for the same participation/problem. Reuse the current workspace trace and submission flow without changing its contract. |
| D4 | Deadline display | Calculate the displayed deadline from server timestamps as `min(participation.started_at + duration_minutes, exam.end_time)`; if duration is null, use `end_time`. Treat the timer as informational; server authorization remains authoritative. |
| D5 | Finalize and submit | Submission ends that coding session as today. Student finalization ends active sessions without creating an automatic submission; timeout auto-submit remains the backend's existing behavior. Confirm before explicit finalization. |
| D6 | Results | Show verdict/score/judge detail only when the submission response sets `result_visible`; never infer visibility in the client. |
| D7 | Error handling | Show API errors for not-yet-open, ended, cancelled or unassigned exams; provide a refresh/re-entry action for recoverable states. Do not bypass backend access decisions. |
| D8 | Verification | Add unit coverage for response mapping/deadline display, API contract coverage for the new scoped endpoint and its hidden-test fence, and Compose Playwright for start → open problem → run/submit → finalize/result-visibility paths at desktop and mobile. |

## 5. Acceptance checks

| ID | Check |
|---|---|
| AC-21B-01 | Student sees only exams assigned to them and the participation state returned by the API. |
| AC-21B-02 | Student can start/resume an exam only within the backend-authorized window and open only problems returned by the student exam endpoint. |
| AC-21B-03 | Exam workspace uses the existing trace/run/submit flow and keeps hidden test data out of the client. |
| AC-21B-04 | The displayed deadline follows the approved server-time rule; post-deadline writes are rejected by the API. |
| AC-21B-05 | Finalization does not create a submission; result details appear only when `result_visible` is true. |
| AC-21B-06 | Frontend typecheck, lint, unit tests, production build, backend endpoint tests and Compose Playwright pass. |
| AC-21B-07 | Student list, problem entry and workspace controls remain operable at desktop and mobile widths without page-level horizontal overflow. |

## 6. Out of scope

- Teacher authoring/observation changes, administrator screens and statistics.
- Changes to exam lifecycle rules, scheduler behavior, judging policy or result-visibility policy.
- Database migrations, unless implementation discovers a contract gap that cannot be solved additively; any such change requires a new decision before coding.
- Visual redesign or polish.

## 7. Lock record

| Check | Result |
|---|---|
| Frontend lint, typecheck, unit tests, production build | PASS — 46 unit tests; build succeeds (existing main-chunk size warning). |
| Backend exam lifecycle tests | PASS — 15 passed. |
| Compose integration and student exam Playwright | PASS — 5 integration tests and 1 desktop/mobile journey test. |
| GitHub CI | PASS — all jobs green on push run `41102040017` and PR run `41102136212`, attempt 2. The initial PR auth run had one concurrent-refresh race failure; the rerun passed. |
| Generated API client | PASS — backend OpenAPI and generated client match. |
| Migration | None. |
| Lock | Recorded in `docs/PROJECT_PROVENANCE_LOG.md`; tag points to the lock PR merge commit. |

Post-merge follow-up: main Compose E2E run `41105789029` caught the student home redirect breaking the existing practice journey. PR #20 (`c8907c1`) restores `/practice` as the student home while keeping exams in navigation; workflow-dispatch run `41106800105` passed the complete CI and Compose E2E suite.
