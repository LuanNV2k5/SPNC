# 35 — TEACHER OBSERVATION (PHASE 09) SPECIFICATION

> **Module:** Teacher Observation, Annotations & Realtime Notification (Phase 09)
> **Status:** APPROVED 2026-10-28 (all §9 recommendations; see PROJECT_PROVENANCE_LOG.md) — IMPLEMENTATION IN PROGRESS
> **Date:** 2026-10-28
> **Parent Baseline:** `phase-08e-session-hardening-locked` (`d2ddfee`)
> **Proposed Branch:** `phase09`
> **Target Lock Tag:** `phase-09-observation-locked`

---

## 1. Purpose

Phase 09 gives TEACHERs read access to the evidence collected by Phases 06–08E, plus their own annotations. It does not add any automated judgment (PROJECT_RULES #20–22; `00_SCOPE.md` NG1–NG2).

| Requirement | Summary | Use case |
|---|---|---|
| REQ-OBS-001 (MUST) | "Needs attention" list: students with `AttentionSignal.status = NEW`, own class only | UC-F01 |
| REQ-OBS-002 (MUST) | Session list per student with problem, context, times, status, actor, latest activity, verdict, signal count | UC-F05 |
| REQ-OBS-003 (MUST) | Session timeline (events incl. `SESSION_ENDED` with actor) | UC-F02 |
| REQ-OBS-004 (MUST) | Code snapshot content at any timeline point | UC-F02 |
| REQ-OBS-005 (MUST) | TeacherAnnotation CRUD; only the owner can update or delete | UC-F03 |
| REQ-OBS-006 (MUST) | 403 if the student is not in the teacher's class | UC-F03 |
| REQ-OBS-007 (SHOULD) | Class/exam statistics from Submission data | UC-F04 |
| REQ-OBS-008 (MUST) | Exam observation overview per student | UC-F06 |
| NFR-REALTIME-001..003 | REST is primary. WebSocket is a notification channel only, never streams source code, and clients resync via REST | OQ-14 |
| RBAC (`05_RBAC_MATRIX.md`) | AttentionSignal READ / ACKNOWLEDGE OWN_CLASS; TeacherAnnotation OWN; Run READ OWN_CLASS | — |

---

## 2. Findings From the Current Code (2026-10-28)

| # | Finding | Location | Impact |
|---|---|---|---|
| F1 | `RunService.get_run` / `list_runs` let **any** TEACHER read any student's runs (no class check). This violates PROJECT_RULES #12 and the RBAC "Run READ OWN_CLASS". | `app/services/run.py:57`, `:75` | **HIGH** (authorization) |
| F2 | `SignalStatus` in code is `NEW / VIEWED / ACK / DISMISSED`. Domain §1.8 says `NEW / ACKNOWLEDGED / DISMISSED`. No code sets anything but `NEW`. | `app/models/observation.py:18` | D1 |
| F3 | The Phase 06 teacher trace endpoints only check "class owner + active membership + session belongs to student". A teacher therefore sees **every** session of that student, including practice on other teachers' problems and exams of other classes. UC-F05 says "filter theo lớp này". | `app/services/trace.py:_authorize_teacher_session` | D2 |
| F4 | `TeacherAnnotation` table already exists (initial schema). No API uses it. | `app/models/observation.py` | reuse, no new table |
| F5 | `ParticipationStatus` has `NOT_STARTED / IN_PROGRESS / COMPLETED / ABANDONED`. UC-F06 also shows `EXPIRED` and `CANCELLED`. | `app/models/exam.py:19` | D6 (derived, no schema change) |
| F6 | There is no Submission creation or judging pipeline, so REQ-OBS-007 statistics would always be empty. | `app/services/academic.py` (read-only) | D5 |
| F7 | Signals are created by the scheduler process and runs by the worker process. The API process that holds teacher WebSockets never sees those writes directly, so it needs a cross-process notification path. | `signal_scheduler.py`, `worker.py` | D4 |
| F8 | The trace timeline orders events by `sequence_number`. REQ-OBS-003 text says "theo server_timestamp". Events in one batch share almost the same `server_timestamp`, so sorting by it would scramble causal order. | `app/repositories/trace.py:get_paginated_history` | D3 |

---

## 3. Session Visibility Rule (core authorization)

A TEACHER `T` may observe session `S` of student `U` **in the context of class `C`** when all of the following hold:
1. `C.owner_id == T.id`;
2. `U` has an active `ClassMembership` in `C`;
3. `S.student_id == U.id`;
4. `S` belongs to class `C` (D2 recommendation):
   - exam session: its exam has an `ExamAssignment` to `C`;
   - practice session: its problem is published to `C` (`ProblemClassPublication`) **or** owned by `T`.

A single helper, `ObservationAuthorizer.authorize_session(db, teacher, class_id, student_id, session_id)`, enforces this rule. Every Phase 09 endpoint uses it, as do the Phase 06 teacher trace and scratchpad endpoints and the teacher run reads (F1, F3). Violations → 403 `FORBIDDEN_RESOURCE`, or 404 when the session is not visible in that class context. All errors keep the `{error_code, message, request_id}` envelope.

Exam-level views (UC-F06) use `Exam.owner_id == T.id` and show only students of classes that are assigned to the exam **and** owned by `T`.

---

## 4. Scope by Sub-phase

### 09A — Observation read API (REST)
| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/v1/classes/{class_id}/attention` | REQ-OBS-001 | Students with ≥1 `NEW` signal on visible sessions. Per student: counts by `signal_type`, latest `detected_at`. Paginated. |
| `GET /api/v1/classes/{class_id}/students/{student_id}/sessions` | REQ-OBS-002 | Visible sessions. Fields: `problem_title`, `context` (exam title / "Practice"), `opened_at`, `ended_at`, `status`, `termination_source`, `latest_meaningful_event_at`, `latest_submission_verdict`, `signal_count`, `final_loc`, `working_time_seconds`. Paginated, newest first. |
| `GET /api/v1/classes/{class_id}/students/{student_id}/sessions/{session_id}/timeline` | REQ-OBS-003 | Trace events (D3 order) + the session's signals (status, type, evidence) + snapshot references. Cursor/paginated. Idle gaps come from persisted `IDLE_DETECTED` signals; nothing is recomputed. |
| `GET /api/v1/classes/{class_id}/students/{student_id}/sessions/{session_id}/snapshots/{snapshot_id}` | REQ-OBS-004 | Snapshot metadata + source code. The snapshot must belong to the session. |
| `GET /api/v1/classes/{class_id}/students/{student_id}/sessions/{session_id}/runs` | RBAC Run READ OWN_CLASS | Teacher run history (input/output/verdict/time). |
| `GET /api/v1/classes/{class_id}/students/{student_id}/signals` | RBAC Signal READ | Filters: `status`, `session_id`, `signal_type`. Paginated. |
| `GET /api/v1/exams/{exam_id}/observation` | REQ-OBS-008 | Per student: participation status (D6 derived), submitted problem count, current session (`opened_at`, latest activity, run count), signal count. Paginated. |
| **Fix F1** | `/my/coding-sessions/{id}/runs*` | Owner STUDENT only. Teachers use the class-scoped endpoint above. |
| **Fix F3** | Phase 06 teacher trace/scratchpad endpoints | Switch to `ObservationAuthorizer` (§3). |

### 09B — Signal status & annotations
| Endpoint | Purpose | Notes |
|---|---|---|
| `PATCH /api/v1/classes/{class_id}/students/{student_id}/signals/{signal_id}` | RBAC ACKNOWLEDGE | Body `{status}` only. Allowed transitions per D1. Evidence and other fields are immutable (DTI-08). Each change writes an AuditLog entry (`SIGNAL_STATUS_CHANGED`, old/new). |
| `POST /api/v1/annotations` | REQ-OBS-005 create | `{student_id, session_id?, signal_id?, content}`. The student must be observable in at least one class owned by the teacher. `session_id` / `signal_id` must belong to that student and be visible (§3). |
| `GET /api/v1/annotations` | REQ-OBS-005 read | Own annotations only. Filters: `student_id`, `session_id`, `signal_id`, `created_from`, `created_to`. Paginated. |
| `PATCH /api/v1/annotations/{id}` | update | Owner only (403 otherwise). Only `content` changes; `updated_at` is set. |
| `DELETE /api/v1/annotations/{id}` | delete | Owner only. Hard vs soft per D7. |

`content` is plain text, 1–5000 chars (D8). It is never logged, consistent with PROJECT_RULES #25.

### 09C — Realtime notification (WebSocket)
- `WS /api/v1/ws/teacher`. The client authenticates with its first message `{type:"auth", access_token}` within 5 s. The token is **not** put in the URL, so access logs never capture it (PROJECT_RULES #25).
- The client subscribes with `{type:"subscribe", class_id}` or `{type:"subscribe", exam_id}`. The server checks ownership (§3) before accepting.
- Server → client messages carry only identifiers and states. No source code, evidence or payload is sent (NFR-REALTIME-002):
  - `signal.created {signal_id, session_id, student_id, signal_type}`
  - `run.completed {run_id, session_id, student_id, verdict}`
  - `session.state {session_id, student_id, status}`
- Cross-process delivery per D4. Delivery is best-effort. After a reconnect, the client must REST-refetch (NFR-REALTIME-003). The database stays the source of truth.

### 09D — Closure
Full regression on fresh PostgreSQL, docs update, lock tag.

### 4.1 Out of Scope (fenced)
- Frontend / Teacher Portal UI (separate phase).
- Student-facing trace/signal access (NG10, REQ-STU-003).
- REQ-OBS-007 statistics, if D5 defers them.
- Shared blob storage (S3/MinIO) for snapshots: still required before deployment (Phase 08D §15.3), proposed as its own infrastructure sub-phase.
- `PATCH /admin/exams/{id}/cancel` vs OQ-23 governance question: raised separately to the Project Owner, not changed here.
- ADMIN observation endpoints, if D9 defers them.

---

## 5. Data Model Changes
- **No new tables.** `teacher_annotations` and `attention_signals` already exist.
- Code-level `SignalStatus` aligned with D1. The column is `String(20)`, so no DDL is needed for the values. A migration is still added for:
  - `ix_attention_signals_student_status` on `(student_id, status)` for the attention query;
  - (D7 = soft delete only) `teacher_annotations.deleted_at TIMESTAMPTZ NULL`;
  - (D4 = PostgreSQL NOTIFY) `AFTER INSERT/UPDATE` triggers that `pg_notify('spnc_observation', <id-only JSON>)` on `attention_signals` insert, `runs` status → COMPLETED/FAILED_*, and `coding_sessions` status change.
- Historical migrations remain untouched.

---

## 6. Privacy & Ethics Invariants
1. Teachers never see sessions outside the §3 rule. That includes peers' code in `LOC_ANOMALY` evidence, which already holds aggregates only.
2. Annotations are the teacher's subjective notes. The API never generates or suggests annotation text.
3. No endpoint returns judgmental wording, and the WebSocket never carries code.
4. Students get no new endpoints. Their trace, signals and annotations remain hidden (REQ-STU-003).

---

## 7. Acceptance Criteria

| ID | Criterion |
|---|---|
| AC-09-01 | Every 09A/09B endpoint returns 403 for a teacher who does not own the class/exam. It returns 403/404 for a student not in the class and for a session outside the §3 rule. |
| AC-09-02 | F1: a TEACHER without class ownership gets 403 on run reads; the owning STUDENT still reads their own runs. |
| AC-09-03 | F3: Phase 06 teacher trace/scratchpad endpoints apply §3 (regression of existing positive tests + new negative tests). |
| AC-09-04 | Attention list contains exactly students with ≥1 `NEW` signal on visible sessions; acknowledged/dismissed signals drop out. |
| AC-09-05 | Session list fields match REQ-OBS-002, including `final_loc`/`working_time_seconds` from 08E and `signal_count`. |
| AC-09-06 | Timeline returns events in D3 order, includes the server `SESSION_ENDED` and the session's signals; pagination is stable. |
| AC-09-07 | Snapshot endpoint returns content only for snapshots of that session. |
| AC-09-08 | Exam observation returns per-student status (incl. derived EXPIRED/CANCELLED per D6), submission count, current session, signal count; only students of the teacher's assigned classes. |
| AC-09-09 | Signal PATCH allows only D1 transitions; evidence unchanged byte-for-byte; AuditLog entry written. |
| AC-09-10 | Annotation CRUD: owner-only update/delete (403 for another teacher); filters work; cross-student `session_id`/`signal_id` rejected (422). |
| AC-09-11 | WebSocket: unauthenticated or late auth closes; subscribing to a foreign class/exam is refused; a committed signal/run/session change reaches a subscribed owner within 5 s; no message contains source code or evidence. |
| AC-09-12 | No student-facing routes added; no UI files. |
| AC-09-13 | Full Phase 03–08E regression passes on fresh databases. |

---

## 8. Implementation Plan (files)

| Step | Files |
|---|---|
| 1 | `app/services/observation_auth.py` (§3 helper); refactor `app/services/trace.py`, `app/services/run.py` |
| 2 | `app/repositories/observation.py`, `app/services/observation.py`, `app/schemas/observation.py`, `app/api/endpoints/observation.py` (09A) |
| 3 | `app/services/annotation.py`, `app/repositories/annotation.py`, schemas/endpoints (09B); signal status service + AuditLog |
| 4 | Migration `phase09_observation` (index, optional `deleted_at`, optional NOTIFY triggers) |
| 5 | `app/realtime/` (WS hub, listener per D4), `app/api/endpoints/ws.py` (09C) |
| 6 | Tests: `tests/api/test_observation.py`, `test_annotations.py`, `test_observation_authz.py`, `test_ws_notifications.py`; extend `test_run.py`, `test_trace.py` |
| 7 | Docs: this file §10 verification record; RBAC matrix amendment if D1 adds DISMISS |

---

## 9. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | `SignalStatus` values and teacher transitions | (a) align code to domain `NEW / ACKNOWLEDGED / DISMISSED`; teacher may set ACKNOWLEDGED or DISMISSED from NEW, and back to NEW; (b) keep code values `VIEWED/ACK` | **(a)**. Domain is authoritative. **DISMISS needs an RBAC amendment** (matrix lists only ACKNOWLEDGE) → recorded as DCR. |
| **D2** | Session visibility in class context (F3) | (a) §3 rule: exam assigned to class, or practice problem published to class / owned by teacher; (b) any session of a student in the class (current Phase 06 behaviour) | **(a)**. Matches UC-F05 "filter theo lớp này" and avoids exposing work done for another teacher. It tightens Phase 06 teacher endpoints. |
| **D3** | Timeline order (F8) | (a) `sequence_number` (causal client order), `server_timestamp` shown on every event; (b) `server_timestamp` | **(a)**. Per-batch server timestamps would reorder events. Recorded as an interpretation of REQ-OBS-003. |
| **D4** | Cross-process notification for WebSocket | (a) PostgreSQL `LISTEN/NOTIFY` via triggers (fires only on commit, no producer code changes); (b) Redis pub/sub published by API/worker/scheduler after commit | **(a)**. Atomic with the data change and no dual-write. Redis stays queue-only (ADR-003). |
| **D5** | REQ-OBS-007 statistics (SHOULD) | (a) defer until the Submission pipeline exists; (b) implement now (always empty) | **(a)**. Without submissions the endpoint would ship untestable numbers. |
| **D6** | `EXPIRED` / `CANCELLED` in exam observation | (a) derived in the response (EXPIRED = not COMPLETED and `now ≥ end_time`; CANCELLED = exam CANCELLED); (b) add enum values + transitions | **(a)**. A view-only derivation with no schema/state-machine change. |
| **D7** | Annotation delete semantics | (a) hard delete; (b) soft delete (`deleted_at`) | **(b)**. Keeps a trail for disputes. Deleted rows are excluded from all reads. |
| **D8** | Annotation content limits | (a) plain text 1–5000 chars; (b) rich text/markdown | **(a)**. Simplest and safe to render. |
| **D9** | ADMIN read access (RBAC lists SYSTEM_WIDE read for signals/timeline/annotations) | (a) defer ADMIN observation endpoints to a later admin phase; (b) include now | **(a)**. Phase 09 is teacher-facing; the RBAC row stays valid for a later phase. |

Approval (all recommendations or with overrides) is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before implementation (PROJECT_RULES #1–3). Proposed order: 09A → 09B → 09C, each verified before the next (PROJECT_RULES #3).

---

## 10. Verification Record

*To be completed at Phase 09 closure.*
