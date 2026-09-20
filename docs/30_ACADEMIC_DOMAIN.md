# Phase 05 — Academic Domain

## Overview

Phase 05 implements the complete academic domain layer for SPNC:

- **Teacher**: Class management, class membership, Problem management (visibility + class publication), Exam management (problem association, class assignment)
- **Student**: Exam access (via class assignment + authoritative server timing), ExamParticipation, Practice CodingSession, Exam CodingSession
- **Foundation**: Submission model access (judge execution deferred to Phase 07)

---

## 30_CLASS_MODULE.md — Class Ownership & Membership

### Class Ownership

- Only **Teacher** role can create, list, update, and view own classes.
- `owner_id` is set from the authenticated teacher's token.
- Knowing a class ID **never** grants access — ownership is always verified.
- Another teacher's class returns **403 CLASS_FORBIDDEN**.

### Class Membership

- Teachers enroll students via `POST /api/v1/classes/{class_id}/members`.
- Target user must have `STUDENT` role; enrolling a non-student returns **422 NOT_A_STUDENT**.
- Duplicate enrollment (same student, same class, active) returns **409 ALREADY_ENROLLED**.
- Removing a student (`DELETE .../members/{student_id}`) deactivates the membership (`is_active=False`).
- Students list enrolled classes via `GET /api/v1/my/classes`.

---

## 31_PROBLEM_MODULE.md — Problem Visibility & Class Publication

### Visibility Model

| Visibility | Teacher Owner | Teacher Other | Student in Published Class | Student Other | Anonymous |
|-----------|:---:|:---:|:---:|:---:|:---:|
| PRIVATE | ✅ | ❌ | ❌ | ❌ | ❌ |
| CLASS | ✅ | ❌ | ✅ (via publication) | ❌ | ❌ |
| PUBLIC | ✅ | ✅ (view only) | ✅ | ✅ | ❌ |

### CLASS Publication

- `POST /api/v1/problems/{problem_id}/publish` — Teacher publishes problem to class.
- **Requirements**: Teacher must own the problem AND the class.
- **Visibility guard**: Problem must have `visibility=CLASS` (or `PUBLIC`) to be published.  
  Publishing a `PRIVATE` problem returns **422 PROBLEM_NOT_CLASS_VISIBLE**.
- Publication does not imply ownership transfer — another teacher cannot edit PUBLIC problems.
- Unpublish: `DELETE /api/v1/problems/{problem_id}/publish/{class_id}` — removes publication; student access revoked.

---

## 32_EXAM_MODULE.md — Exam Ownership & Association

### Exam Ownership

- Teachers create exams with explicit `start_time` and `end_time`.
- DB enforces `end_time > start_time` via check constraint.
- Materialized `status` field exists for reporting but **must not be used for authorization**.

### Exam–Problem Association

- `POST /api/v1/exams/{exam_id}/problems` — Teacher attaches own problem to own exam.
- Teacher must own both exam and problem; cross-ownership returns 403.
- Unique constraint: same (exam_id, problem_id) pair and same (exam_id, order_index) pair.

### Exam–Class Assignment

- `POST /api/v1/exams/{exam_id}/classes` — Teacher assigns own class to own exam.
- Teacher must own both exam and class; cross-ownership returns 403.
- Unique constraint: same (exam_id, class_id) pair.

---

## 33_EXAM_TIMING.md — Authoritative Exam Timing

### Rule (CRITICAL)

Authorization **always** evaluates directly against `start_time` and `end_time` stored in the database. The materialized `status` field is **never** used for access control decisions.

### Boundary Behavior

| Server Time | Result |
|------------|--------|
| `now < start_time` | `403 EXAM_NOT_STARTED` |
| `start_time <= now < end_time` | ✅ Access granted |
| `now >= end_time` | `403 EXAM_ENDED` |
| `status == CANCELLED` (any time) | `403 EXAM_CANCELLED` |

### Evidence (P05-E23)

Test `P05-E23` proves this: materialized status is set to `SCHEDULED` (incorrect) while the real timing says the exam is active → student can still start. Authorization uses raw timestamps only.

---

## 34_EXAM_PARTICIPATION.md — ExamParticipation

### Start Exam Flow

```
Student POST /api/v1/my/exams/{exam_id}/start
  → Verify exam exists & NOT CANCELLED
  → Verify now ∈ [start_time, end_time) (authoritative)
  → Verify student in assigned class (membership check)
  → Idempotent: existing participation returned as-is
  → CREATE participation with status=IN_PROGRESS
    (DB unique constraint handles concurrent double-create)
```

### Concurrency Safety

The DB unique constraint on `(exam_id, student_id)` in `exam_participations` is the concurrency gate.  
On `IntegrityError` from a concurrent insert, the endpoint rolls back and fetches the existing participation.  
This guarantees exactly **ONE** `ExamParticipation` regardless of concurrent requests.

### Test: P05-D09

A `threading.Barrier(4)` synchronizes 4 concurrent threads, each with an independent HTTP client and DB connection, all calling `start_exam` simultaneously. The DB count invariant (`count == 1`) is verified after all complete.

---

## 35_PRACTICE_SESSION.md — Practice CodingSession Foundation

### Active Exam Guard (ACTIVE_EXAM_IN_PROGRESS)

Before creating a Practice session, the server checks:

```python
get_active_exam_participation_for_student(db, student_id)
```

This query joins `ExamParticipation → Exam` and checks:
- `participation.status == IN_PROGRESS`
- `exam.start_time <= now < exam.end_time`
- `exam.status != CANCELLED`

If any result: **403 ACTIVE_EXAM_IN_PROGRESS**.

### Scenarios (all tested)

| Scenario | Practice Allowed? |
|---------|:---:|
| Active exam (IN_PROGRESS participation, within window) | ❌ |
| Future exam (not started yet) | ✅ |
| Ended exam (window passed) | ✅ |
| Cancelled exam | ✅ |

### Problem Access for Practice

| Problem Visibility | Access |
|-------------------|--------|
| PRIVATE | ❌ 403 PROBLEM_FORBIDDEN |
| CLASS (published to student's class) | ✅ |
| CLASS (not published to student's class) | ❌ 403 PROBLEM_FORBIDDEN |
| PUBLIC | ✅ |

---

## 36_EXAM_SESSION.md — Exam CodingSession Foundation

### Requirements

- Valid `ExamParticipation` belonging to the student
- Participation `status == IN_PROGRESS`
- Exam is currently active (authoritative server timing)
- Problem must appear in `exam_problems` for that exam
- Language must be in problem's `supported_languages`

### Endpoint

```
POST /api/v1/my/exam-sessions?participation_id={uuid}
Body: { "problem_id": uuid, "language": "CPP17" | "PYTHON3" }
```

---

## 37_SESSION_LIFECYCLE.md — Session Lifecycle

### States

```
ACTIVE → ENDED     (normal: student clicks submit/end)
ACTIVE → ENDED     (system exam timeout: SYSTEM_EXAM_TIMEOUT)
ACTIVE → ABANDONED (system policy: SYSTEM_SESSION_POLICY)
```

**ABANDONED ≠ failure.** It is a valid terminal state.

### Termination Sources

| Source | Meaning |
|--------|---------|
| `STUDENT` | Student explicitly ended the session |
| `SYSTEM_EXAM_TIMEOUT` | Exam window closed |
| `SYSTEM_SESSION_POLICY` | System policy (not student action) |

### Important: No Inactivity Auto-Abandon

Five minutes of inactivity does **NOT** automatically abandon a Practice session in Phase 05.  
This is deferred per project scope.

---

## 38_SUBMISSION_FOUNDATION.md — Submission Foundation

- Students can `GET /api/v1/my/submissions` and `GET /api/v1/my/submissions/{id}`.
- Submissions are created by the judge (Phase 07). Phase 05 only provides read access.
- Cross-student access blocked: 403 SUBMISSION_FORBIDDEN.
- No judge execution happens in Phase 05 (never in FastAPI).

---

## 39_AUTHORIZATION_MATRIX.md — Authorization Matrix

### Role Summary

| Action | ADMIN | TEACHER | STUDENT | Anonymous |
|--------|:-----:|:-------:|:-------:|:---------:|
| Create Class | ❌ | ✅ (own) | ❌ | ❌ |
| Manage Members | ❌ | ✅ (own class) | ❌ | ❌ |
| Create Problem | ❌ | ✅ | ❌ | ❌ |
| Publish Problem | ❌ | ✅ (own class+prob) | ❌ | ❌ |
| Create Exam | ❌ | ✅ | ❌ | ❌ |
| Attach Exam Problem | ❌ | ✅ (own) | ❌ | ❌ |
| Assign Exam Class | ❌ | ✅ (own) | ❌ | ❌ |
| List accessible exams | ❌ | ❌ | ✅ (via class) | ❌ |
| Start exam | ❌ | ❌ | ✅ (assigned+timing) | ❌ |
| Practice session | ❌ | ❌ | ✅ (problem access) | ❌ |
| Exam session | ❌ | ❌ | ✅ (participation) | ❌ |

---

## 40_ACADEMIC_API.md — API Reference

### Class API

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/v1/classes` | Teacher | Create class |
| GET | `/api/v1/classes` | Teacher | List own classes |
| GET | `/api/v1/classes/{id}` | Teacher | Get class (owner only) |
| PATCH | `/api/v1/classes/{id}` | Teacher | Update class (owner only) |
| POST | `/api/v1/classes/{id}/members` | Teacher | Enroll student |
| GET | `/api/v1/classes/{id}/members` | Teacher | List members |
| DELETE | `/api/v1/classes/{id}/members/{student_id}` | Teacher | Remove student |
| GET | `/api/v1/my/classes` | Student | List enrolled classes |

### Problem API

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/v1/problems` | Teacher | Create problem |
| GET | `/api/v1/problems` | Teacher | List own problems |
| GET | `/api/v1/problems/{id}` | Teacher/Student | Get problem (visibility rules) |
| PATCH | `/api/v1/problems/{id}` | Teacher | Update problem (owner only) |
| GET | `/api/v1/problems/public/bank` | Any | Browse PUBLIC problems |
| POST | `/api/v1/problems/{id}/publish` | Teacher | Publish to class |
| DELETE | `/api/v1/problems/{id}/publish/{class_id}` | Teacher | Unpublish from class |

### Exam API

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/v1/exams` | Teacher | Create exam |
| GET | `/api/v1/exams` | Teacher | List own exams |
| GET | `/api/v1/exams/{id}` | Teacher | Get exam (owner only) |
| PATCH | `/api/v1/exams/{id}` | Teacher | Update exam (owner only) |
| POST | `/api/v1/exams/{id}/problems` | Teacher | Attach problem |
| GET | `/api/v1/exams/{id}/problems` | Teacher | List exam problems |
| DELETE | `/api/v1/exams/{id}/problems/{pid}` | Teacher | Detach problem |
| POST | `/api/v1/exams/{id}/classes` | Teacher | Assign class |
| GET | `/api/v1/exams/{id}/classes` | Teacher | List assigned classes |
| DELETE | `/api/v1/exams/{id}/classes/{cid}` | Teacher | Unassign class |
| GET | `/api/v1/my/exams` | Student | List accessible exams |
| POST | `/api/v1/my/exams/{id}/start` | Student | Start exam (create participation) |
| GET | `/api/v1/my/exams/{id}/participation` | Student | Get own participation |

### Practice Session API

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/v1/my/practice/sessions` | Student | Start practice session |
| GET | `/api/v1/my/practice/sessions` | Student | List practice sessions |
| GET | `/api/v1/my/practice/sessions/{id}` | Student | Get session detail |
| POST | `/api/v1/my/practice/sessions/{id}/end` | Student | End session |

### Exam Session API

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/v1/my/exam-sessions?participation_id={uuid}` | Student | Start exam session |
| GET | `/api/v1/my/exam-sessions/{id}` | Student | Get session detail |
| POST | `/api/v1/my/exam-sessions/{id}/end` | Student | End session |

### Submission API (Foundation)

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/api/v1/my/submissions` | Student | List submissions |
| GET | `/api/v1/my/submissions/{id}` | Student | Get submission detail |

---

## 41_ACADEMIC_TESTING.md — Tests & Traceability

### Test Groups

| Group | IDs | Count | Description |
|-------|-----|-------|-------------|
| P05-C | C01–C15 | 15 | Class management |
| P05-P | P01–P15 | 15 | Problem management |
| P05-E | E01–E25 | 25 | Exam management + participation |
| P05-S | S01–S15 | 15 | Session management |
| P05-A | A01–A10 | 10 | Authorization matrix |
| P05-D | D01–D10 | 10 | DB invariants |

**Total**: 90 tests

### Key Traceability

| Test ID | Requirement Proven |
|---------|-------------------|
| P05-C01 | Teacher creates class with correct owner_id |
| P05-C02 | Teacher only sees own classes |
| P05-C03 | Cross-teacher class access blocked |
| P05-C05 | Student enrollment with role verification |
| P05-C06 | Duplicate enrollment prevention |
| P05-C13 | Stale token with locked account rejected |
| P05-P03 | PRIVATE problem blocked from other teacher |
| P05-P08 | Cannot publish PRIVATE problem to class |
| P05-P09 | CLASS publication unlocks student access |
| P05-P10 | Student not in class cannot see CLASS problem |
| P05-P13 | PUBLIC problem edit blocked for non-owner |
| P05-E09 | EXAM_NOT_STARTED with authoritative timing |
| P05-E10 | EXAM_ENDED with authoritative timing |
| P05-E13 | EXAM_CANCELLED blocks start |
| P05-E14 | Idempotent exam start |
| P05-E21 | Boundary: 1 second after start → success |
| P05-E23 | Materialized status ignored for timing |
| P05-E24 | Future exam does NOT block practice |
| P05-E25 | Ended exam does NOT block practice |
| P05-S02 | ACTIVE_EXAM_IN_PROGRESS blocks practice |
| P05-S03 | Cancelled exam does NOT block practice |
| P05-A01 | All anonymous requests → 401 |
| P05-A05 | Knowing ID ≠ access |
| P05-D02 | DB unique constraint on ExamParticipation |
| P05-D09 | Real concurrency proof (4 threads, barrier) |

---

## 42_ACADEMIC_TRACEABILITY.md — Phase Boundary

### Phase 06 Deferred Scope

- Editor timeline capture (TraceEvent)
- Code snapshot management (CodeSnapshot)
- Attention signals (AttentionSignal)
- Teacher annotations
- Student replay / audit trail
- Raw digital trace exposure

### Phase 07 Deferred Scope

- Docker Judge integration
- Compiler/interpreter execution
- Run creation and polling
- Verdict evaluation
- Score calculation
- Judge Redis queue
- Execution generation / lease semantics

---

*Phase 05 implementation complete. See [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) for policy gaps.*
