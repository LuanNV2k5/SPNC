# 40 — DECISIONS FOR OQ-16, OQ-26, OQ-27 (PHASE 14) PROPOSAL

> **Module:** Practice points (REQ-STU-004), production judge isolation, exam duration semantics
> **Status:** APPROVED 2026-10-29 (Q1–Q5 as recommended; see PROJECT_PROVENANCE_LOG.md) — IMPLEMENTED AND VERIFIED 2026-10-29 (§6); lock tag pending Project Owner review
> **Date:** 2026-10-29
> **Parent Baseline:** `phase-13-backend-complete-locked` (`409cd97`)
> **Proposed Branch:** `phase14`
> **Target Lock Tag:** `phase-14-open-questions-locked`

---

## 1. Purpose

Three questions are still open after the Phase 13 lock. Each one blocks either a requirement or a deployment:

| OQ | Blocks | Today |
|---|---|---|
| OQ-16 Points mechanism | REQ-STU-004 (SHOULD), UC-G02, goal G8 | Not implemented |
| OQ-26 Production judge isolation | Any production deployment (docs/10 §2 "Highly Untrusted Execution Zone") | Demo stack mounts the host Docker socket into the worker (docs/37 D3) |
| OQ-27 Meaning of `duration_minutes` | REQ-EXAM-001 semantics | Implemented under an assumption (docs/38 D7) |

This document proposes an answer for each. Once you decide, the answers are recorded in `OPEN_QUESTIONS.md` and `PROJECT_PROVENANCE_LOG.md`, and §4 becomes the Phase 14 implementation scope.

---

## 2. Constraints That Shape the Options

- **No judgment of students** (NG1, NG2, PROJECT_RULES #20–22): points must not become a ranking or a competence label.
- **Exam result visibility** (docs/36 D14): exam verdicts stay hidden until ENDED + `allow_view_result_after`. Points earned in an exam would reveal results early.
- **Students never see trace or signals** (REQ-STU-003): points must come from verdicts only, never from trace or signals.
- **No Kubernetes in V1** (docs/10 §1): Docker Compose or an equivalent such as ECS or Swarm.
- **The sandbox already enforces** network off, CPU/memory/pids limits and uid 1000 (Rules 18–19). The OQ-26 risk is the worker's access to the container runtime, not the sandbox limits.

---

## 3. Options

### 3.1 OQ-16 — Points

| Option | Rule | Pros | Cons |
|---|---|---|---|
| **A** | **Practice only. A student earns points once per problem, on their first ACCEPTED submission: EASY 10, MEDIUM 20, HARD 30, no difficulty 10. Cumulative, never reset. Visible to the student and to the teacher of a class they belong to. No leaderboard.** | Cannot be farmed by resubmitting. No exam leak. No ranking, so nothing reads as a judgment. Uses the difficulty added in Phase 12. | A fairly simple motivator. |
| B | Practice only, points = the best judged score (0–100) per problem | Rewards partial progress | Partial scores invite gaming on hidden tests; harder to explain |
| C | Practice and exam | More points | Leaks exam results before D14 allows it; mixes assessment with gamification |
| D | Drop REQ-STU-004 from V1 (OUT_OF_SCOPE, like OQ-25) | No work | Goal G8 is not met |

Sub-questions (only for A or B):
- **Leaderboard:** none (recommended), class-only opt-in, or global. A leaderboard ranks students, which conflicts with the spirit of NG1/NG2.
- **Reset:** never (recommended) or per academic year.
- **Problem later deleted or edited:** points already awarded stay (they are history, like submissions).

### 3.2 OQ-26 — Production judge isolation

| Option | Setup | Isolation | Cost |
|---|---|---|---|
| **A** | **Dedicated judge host (VM) per docs/10: the judge worker runs with that host's own Docker daemon. API, database, Redis and MinIO run elsewhere and never expose a container runtime. Sandbox containers use the gVisor runtime (`runsc`) as a second layer. The worker uses a least-privilege PostgreSQL role (read problems/test cases/snapshots/exams; write only runs, submissions and the exam total).** | A sandbox escape reaches only a disposable judge VM, and gVisor makes an escape much harder. The core zone holds no Docker socket. | One more VM. gVisor must be installed on that host. Worker credentials split. |
| B | Rootless Docker on the judge host (no gVisor) | Daemon not root, but shares the kernel with the host | Some images and limits behave differently under rootless mode |
| C | Remote Docker over mutual TLS from the core zone to a judge daemon | Same as A for the daemon; adds a network control channel | Certificate management; the core zone can still drive containers |
| D | Keep the demo layout (socket mount) in production | None | Violates docs/10 §2 |

Code impact of A is small: a `JUDGE_CONTAINER_RUNTIME` setting passed to container creation (default empty = Docker's default, so dev and demo are unchanged), a judge-host compose file without the core services, a role-creation SQL script for the worker, and a deployment section in RUNBOOK. gVisor cannot be verified on the current Windows/Docker Desktop machine; the code path is tested with a fake runtime name and verified on a Linux judge host when one exists.

### 3.3 OQ-27 — `duration_minutes`

| Option | Deadline per student | Notes |
|---|---|---|
| **A** | **`min(started_at + duration, end_time)`; null = window only** | **Implemented and tested in Phase 12 (docs/38 D7). Late starters get less time; nobody works past `end_time`.** |
| B | `started_at + duration` even past `end_time` (so `end_time` = last moment to *start*) | Every student gets the full duration. The exam ENDS later than `end_time`, which changes the scheduler, D14 timing and the meaning of `end_time` in REQ-EXAM-002/003. |
| C | Informational only; the window is the only limit | Simplest. The field exists but does nothing. |

---

## 4. Phase 14 Scope If the Recommendations Are Accepted

| Item | Work |
|---|---|
| Points (OQ-16 A) | Migration: `point_awards` (student, problem, submission, points, awarded_at; UNIQUE(student, problem)). The judge worker awards points in the same transaction as the fenced result write when the result is COMPLETED + ACCEPTED, the submission has no exam, and the source is STUDENT. `GET /my/points` (total + awards). Teacher view of a class member's total via the class-scoped student endpoint. Points are never shown in statistics rankings. |
| Judge isolation (OQ-26 A) | `JUDGE_CONTAINER_RUNTIME` setting; `deploy/judge-host/docker-compose.yml` (worker only); `deploy/sql/judge_worker_role.sql`; RUNBOOK §8 "Production judge host". |
| Duration (OQ-27 A) | Docs only: OQ-27 resolved in OPEN_QUESTIONS and the provenance log. docs/38 stays locked unchanged; its D7 behaviour is now the decision, not an assumption. |

Tests: points awarded once, not for exams, not for WRONG_ANSWER, not for SYSTEM_EXAM_TIMEOUT, idempotent under duplicate delivery and stale generations; runtime passed through to container creation; full regression.

---

## 5. Decisions Requested

| ID | Question | Recommendation |
|---|---|---|
| **Q1** | OQ-16 mechanism: A / B / C / D | **A** |
| **Q2** | Leaderboard | **None** |
| **Q3** | Points reset | **Never** |
| **Q4** | OQ-26 isolation: A / B / C / D | **A** (dedicated judge VM + gVisor + least-privilege DB role) |
| **Q5** | OQ-27 meaning: A / B / C | **A** (confirm the Phase 12 behaviour) |

---

## 6. Verification Record

### 6.1 Changes (2026-10-29)
| Item | Commit | Files |
|---|---|---|
| Decisions | `793cbb1` | OPEN_QUESTIONS (OQ-16, OQ-26, OQ-27 resolved), PROJECT_PROVENANCE_LOG |
| 14A points | `3aea9a9` | migration `b2d8f5a9c314`; `PointTransaction.problem_id/submission_id`; `services/points.py`; `schemas/points.py`; `api/endpoints/points.py`; `services/submission.py` (award in the judge transaction) |
| 14B judge isolation | `7c30625` | `JUDGE_CONTAINER_RUNTIME` (config + `judge/sandbox.py`); `deploy/sql/judge_worker_role.sql`; `deploy/judge-host/docker-compose.yml`; RUNBOOK §8 |

### 6.2 Notes and Deviations
- **Ledger table:** §4 named a new `point_awards` table. The Phase 02 schema already had an unused `point_transactions` ledger (student, signed amount, reason, source reference), so 14A reuses it instead of adding a duplicate. It adds `problem_id`/`submission_id` and a partial unique index `(student_id, problem_id) WHERE reason = 'PRACTICE_ACCEPTED'`. Behaviour is as decided; the signed amount leaves room for later corrections.
- **Award rule:** in `judge_submission`, after the fenced write succeeds with COMPLETED, for a submission with no exam, source STUDENT and verdict ACCEPTED: `INSERT … ON CONFLICT DO NOTHING`. Same transaction as the result, so a stale generation or rollback never awards. Points: EASY 10, MEDIUM 20, HARD 30, none 10.
- **Read APIs:** `GET /my/points` (student) and `GET /classes/{c}/students/{s}/points` (owner teacher, active member) return `{student_id, total, transactions[]}`. There is no ranking or leaderboard endpoint.
- **Role script gaps found by the role test:** `INSERT … ON CONFLICT` against a partial index needs SELECT on the inferred columns, and the Phase 09C run notify trigger (which runs with the caller's privileges) reads `coding_sessions.student_id`. Both are granted at column level only.
- **gVisor not exercised on this machine** (Windows / Docker Desktop). The runtime setting is verified to reach container creation; real `runsc` execution must be confirmed on a Linux judge host (RUNBOOK §8 step 6).

### 6.3 Verification
| Check | Environment | Result |
|---|---|---|
| Migration `b2d8f5a9c314` | Empty DB, PostgreSQL 16.15 | up / down / up OK; partial unique index as specified |
| 14A `test_phase14a_points.py` | Disposable PostgreSQL 16.15, `spnc_phase10_submission_test` | **5 passed** (once per problem, difficulty values, none for WRONG_ANSWER / FAILED_INTERNAL / exam, stale generation and duplicate delivery award once, points survive problem deletion, teacher scope) |
| 14B `tests/infra/test_judge_isolation.py` | same | **11 passed** (runtime pass-through and default; practice, exam and Run jobs complete as `spnc_judge`; 8 forbidden statements denied) |
| Full regression Phase 03–14 | Fresh per-phase DBs migrated to head; Redis; Docker sandbox; MinIO | **527 passed, 0 failed** (43 files) |
| Demo compose stack rebuilt from `phase14` | Docker Desktop (Windows host) | migration applied; E2E **4 passed**; live: two ACCEPTED submissions on a HARD problem → total 30, one award |
