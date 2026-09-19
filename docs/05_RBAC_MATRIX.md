# 05 — RBAC MATRIX

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline
> **Date:** 2026-09-19
> **Status:** DRAFT — Phase 00 Baseline

---

## Legend

| Symbol | Meaning |
|--------|---------|
| `ALLOW` | Unconditionally allowed for this role |
| `DENY` | Never allowed for this role |
| `OWN` | Allowed only for own resource (actor_id = resource.owner_id) |
| `OWN_CLASS` | Allowed only for resources in a Class the actor owns/teaches |
| `CLASS_MEMBER` | Allowed only if actor is enrolled in the Class |
| `OWN_SESSION` | Allowed only for Sessions the actor created |
| `SYSTEM_WIDE` | ADMIN can access all instances system-wide |
| `SYSTEM` | Only internal system processes (scheduler, signal engine) |
| `—` | Not applicable |

---

## Notes

1. **Authorization is enforced at backend.** Frontend hide/show is NOT authorization.
2. **ADMIN SYSTEM_WIDE READ** applies to metadata/management view, not necessarily content editing.
3. **STUDENT DENY on Trace READ** enforces DTI-12 / NG10: raw trace viewer is OUT-OF-SCOPE V1.
4. All DENY entries must return HTTP 403 (not 404) to prevent information leakage about resource existence — except where 404 is intentional to hide existence.
5. Conditions noted with `*` have additional authorization rules listed in the section below.

---

## Resource: User

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | ALLOW | DENY | DENY | REQ-USER-001 |
| READ (self) | ALLOW | OWN | OWN | Any user reads own profile |
| READ (list) | SYSTEM_WIDE | DENY | DENY | ADMIN only; REQ-USER-005 |
| READ (other) | SYSTEM_WIDE | DENY | DENY | ADMIN reads any user |
| UPDATE (profile/self) | OWN | OWN | OWN | REQ-USER-008: password change; any user edits own profile |
| UPDATE (role/status) | SYSTEM_WIDE | DENY | DENY | REQ-USER-004; REQ-USER-002: role/status = ADMIN only |
| DELETE | DENY | DENY | DENY | No user deletion in V1 (soft lock only) |
| LOCK/UNLOCK | SYSTEM_WIDE | DENY | DENY | REQ-USER-002; UC-A04 |

---

## Resource: Class

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY* | ALLOW | DENY | ADMIN does not create classes; REQ-CLASS-001 |
| READ (list) | SYSTEM_WIDE | OWN | DENY | TEACHER sees own classes; ADMIN sees all; REQ-USER-010 |
| READ (detail) | SYSTEM_WIDE | OWN_CLASS | CLASS_MEMBER | STUDENT sees class they enrolled in |
| UPDATE | SYSTEM_WIDE | OWN_CLASS | DENY | REQ-CLASS-002; OWN_CLASS = TEACHER is owner |
| ARCHIVE/CLOSE | SYSTEM_WIDE | OWN_CLASS | DENY | Cannot archive if Exam ONGOING |
| DELETE | DENY | DENY | DENY | No class deletion in V1 |
| READ (system-wide metadata) | SYSTEM_WIDE | DENY | DENY | REQ-USER-010: ADMIN overview |

---

## Resource: ClassMembership (Enrollment)

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE (join by code) | DENY | DENY | ALLOW | REQ-CLASS-005; STUDENT joins via invite_code |
| CREATE (add student) | SYSTEM_WIDE | OWN_CLASS | DENY | TEACHER can add; OQ-08 pending |
| READ (list of students) | SYSTEM_WIDE | OWN_CLASS | OWN | TEACHER sees class roster; STUDENT sees own memberships |
| UPDATE (remove/REMOVED) | SYSTEM_WIDE | OWN_CLASS | DENY | REQ-CLASS-004; soft delete |
| DELETE (hard) | DENY | DENY | DENY | No hard delete; trace must be preserved |

---

## Resource: Problem

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | ALLOW | DENY | REQ-PROB-001; ADMIN does not create problems in V1 |
| READ (PRIVATE) | SYSTEM_WIDE | OWN | DENY | Only author TEACHER + ADMIN |
| READ (CLASS) | SYSTEM_WIDE | OWN_CLASS* | CLASS_MEMBER* | *Only if ClassProblemPublication exists for actor's class; REQ-PROB-007 |
| READ (PUBLIC) | SYSTEM_WIDE | ALLOW | CLASS_MEMBER** | **STUDENT must be enrolled in at least one class; OQ-10 |
| UPDATE | SYSTEM_WIDE | OWN | DENY | REQ-PROB-004; not when Exam SCHEDULED/ONGOING |
| DELETE | SYSTEM_WIDE | OWN | DENY | REQ-PROB-005; not when Exam ACTIVE/ONGOING |
| PUBLISH to CLASS | DENY | OWN | DENY | Create ClassProblemPublication; UC-C03 |

---

## Resource: TestCase

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE/UPDATE/DELETE | SYSTEM_WIDE | OWN (problem) | DENY | REQ-PROB-002 |
| READ (sample, is_sample=true) | SYSTEM_WIDE | OWN | CLASS_MEMBER | Shown during problem view |
| READ (hidden, is_sample=false) | SYSTEM_WIDE | OWN | DENY | Never exposed to STUDENT |

---

## Resource: ProblemBank

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| READ | SYSTEM_WIDE | OWN | DENY | TEACHER manages own bank; REQ-PROB-006 |
| MANAGE (add/remove items) | DENY | OWN | DENY | TEACHER manages own bank only |

---

## Resource: Exam

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | OWN_CLASS | DENY | REQ-EXAM-001; TEACHER must own the Class |
| READ (DRAFT/SCHEDULED) | SYSTEM_WIDE | OWN_CLASS | DENY | STUDENT cannot see Exam before ONGOING |
| READ (ONGOING) | SYSTEM_WIDE | OWN_CLASS | CLASS_MEMBER | STUDENT must be enrolled; REQ-EXAM-005 |
| READ (ENDED, allow=true) | SYSTEM_WIDE | OWN_CLASS | CLASS_MEMBER | Results visible only if allow_view_result_after=true |
| READ (ENDED, allow=false) | SYSTEM_WIDE | OWN_CLASS | DENY | REQ-EXAM-007 |
| READ (CANCELLED) | SYSTEM_WIDE | OWN_CLASS | DENY | Cancelled exams not visible to STUDENT |
| READ (system-wide list) | SYSTEM_WIDE | DENY | DENY | REQ-USER-010: ADMIN overview only |
| UPDATE (content) | DENY | OWN_CLASS* | DENY | *Only when status=DRAFT; REQ-EXAM-006 |
| CANCEL | DENY | OWN_CLASS* | DENY | *Only DRAFT/SCHEDULED; UC-D05; REQ-EXAM-010; OQ-23 for ONGOING |
| PUBLISH | DENY | OWN_CLASS | DENY | UC-D02; sets status=SCHEDULED |
| OBSERVE (exam dashboard) | SYSTEM_WIDE | OWN_CLASS | DENY | UC-F06; REQ-OBS-008 |

---

## Resource: ExamParticipation

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | DENY | CLASS_MEMBER* | *Exam must be ONGOING; REQ-EXAM-009 |
| READ (own) | SYSTEM_WIDE | OWN_CLASS | OWN | STUDENT reads own participation |
| READ (all in exam) | SYSTEM_WIDE | OWN_CLASS | DENY | TEACHER observes all participations; REQ-OBS-008 |
| UPDATE (status by system) | DENY | DENY | DENY | Only SYSTEM scheduler updates status |
| UPDATE (finalize by student) | DENY | DENY | OWN | STUDENT marks COMPLETED when done |

---

## Resource: CodingSession

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | DENY | OWN | System creates on problem open; STUDENT initiates; UC-E02 |
| READ (own) | SYSTEM_WIDE | OWN_CLASS* | OWN | *TEACHER reads sessions of their class students only; REQ-OBS-002 |
| READ (list of student sessions) | SYSTEM_WIDE | OWN_CLASS | DENY | TEACHER browses student session list; UC-F05 |
| OBSERVE (timeline) | SYSTEM_WIDE | OWN_CLASS | DENY | TEACHER views timeline; UC-F02; DTI-12 |
| UPDATE (status by system) | DENY | DENY | DENY | Only SYSTEM scheduler/engine updates Session.status |

---

## Resource: TraceEvent

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE (ingest) | DENY | DENY | OWN_SESSION | Client sends trace; REQ-TRACE-001 to REQ-TRACE-010 |
| READ | SYSTEM_WIDE | OWN_CLASS | DENY | STUDENT cannot read raw trace in V1; DTI-12; NG10; REQ-STU-003 |
| UPDATE | DENY | DENY | DENY | Append-only; DTI-01; REQ-TRACE-008 |
| DELETE | DENY | DENY | DENY | Append-only; DTI-01 |

---

## Resource: CodeSnapshot

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | DENY | SYSTEM* | *System creates on RUN/SUBMIT/CHECKPOINT; not direct student API |
| READ (teacher view) | SYSTEM_WIDE | OWN_CLASS | DENY | TEACHER views snapshot in timeline; REQ-OBS-004 |
| READ (student own submission) | SYSTEM_WIDE | OWN_CLASS | OWN* | *STUDENT reads snapshot via Submission history only; UC-G01 |
| UPDATE | DENY | DENY | DENY | Immutable; DTI-02; REQ-TRACE-014 |
| DELETE | DENY | DENY | DENY | Immutable; DTI-02 |

---

## Resource: Run (RUN_EXECUTED result)

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| EXECUTE | DENY | DENY | OWN_SESSION | STUDENT runs code in own session; UC-E02 |
| READ (own result) | SYSTEM_WIDE | OWN_CLASS | OWN | STUDENT sees own run result; TEACHER views in timeline |
| READ (other's result) | SYSTEM_WIDE | OWN_CLASS | DENY | STUDENT cannot see other's run results |

---

## Resource: Submission

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | DENY | OWN_SESSION* | *During Exam: ExamParticipation must be IN_PROGRESS; REQ-TRACE-012 |
| READ (own) | SYSTEM_WIDE | OWN_CLASS | OWN* | *STUDENT reads own if allowed; OQ-15 for conditions |
| READ (all in class) | SYSTEM_WIDE | OWN_CLASS | DENY | TEACHER views submissions for grading/observation |
| UPDATE (verdict by system) | DENY | DENY | DENY | Only Code Runner + System update verdict |
| DELETE | DENY | DENY | DENY | Submissions are immutable records |

---

## Resource: AttentionSignal

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | DENY | DENY | Only internal SYSTEM (Signal Engine) creates; UC-E03 |
| READ | SYSTEM_WIDE | OWN_CLASS | DENY | TEACHER reads signals for own class students; DTI-12; REQ-STU-003 |
| ACKNOWLEDGE (status → ACKNOWLEDGED) | DENY | OWN_CLASS | DENY | TEACHER acknowledges signal; UC-F01 |
| UPDATE (evidence) | DENY | DENY | DENY | Signal evidence is immutable; DTI-08 |
| DELETE | DENY | DENY | DENY | Signal records preserved |

---

## Resource: TeacherAnnotation

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | DENY | OWN_CLASS* | DENY | *Only for students in TEACHER's class; REQ-OBS-005; UC-F03-A |
| READ (own list) | SYSTEM_WIDE | OWN | DENY | TEACHER reads annotations they created; UC-F03-B |
| READ (others') | SYSTEM_WIDE | DENY | DENY | TEACHER cannot read other TEACHER's annotations |
| UPDATE | DENY | OWN | DENY | Only creator TEACHER; REQ-OBS-005; UC-F03-C |
| DELETE | DENY | OWN | DENY | Only creator TEACHER; REQ-OBS-005; UC-F03-D |

---

## Resource: AuditLog

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| CREATE | SYSTEM | DENY | DENY | Only system (API handlers) create audit entries |
| READ | ALLOW | DENY | DENY | REQ-USER-006; UC-A06; ADMIN only |
| UPDATE | DENY | DENY | DENY | Append-only |
| DELETE | DENY | DENY | DENY | Append-only; legal requirement |

---

## Resource: SystemSetting

| Action | ADMIN | TEACHER | STUDENT | Condition / Notes |
|--------|-------|---------|---------|-------------------|
| READ | ALLOW | DENY | DENY | ADMIN reads system config |
| UPDATE | ALLOW | DENY | DENY | REQ-USER-007; UC-A07; with AuditLog |

---

## Authorization Enforcement Summary

| Rule | Source |
|------|--------|
| Backend enforces ALL authorization | PROJECT_RULES #9; REQ-AUTH-006 |
| AccountStatus checked server-side on every protected request | REQ-AUTH-007; B14 |
| TEACHER scope locked to own Class | PROJECT_RULES #12; DI-6 |
| STUDENT raw trace = DENY in V1 | NG10; DTI-12; REQ-STU-003 |
| Signal evidence immutable | DTI-08; DI-10 |
| Trace events append-only | DTI-01; REQ-TRACE-008 |
| Snapshots immutable | DTI-02; REQ-TRACE-014 |
| Exam timeout server-enforced | DTI-10; REQ-SESSION-003 |
| AttentionSignal: system-created only | UC-E03; REQ-SIGNAL-004 |

---

## Changelog

| Version | Date | Thay đổi |
|---------|------|----------|
| 0.2 | 2026-09-19 | Tạo mới — fix Mi-08; B17 |
| 0.3 | 2026-09-19 | Final Phase 00 Baseline |
