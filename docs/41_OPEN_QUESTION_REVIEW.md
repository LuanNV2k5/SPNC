# 41 — REVIEW OF THE REMAINING OPEN QUESTIONS (STEP 0)

> **Scope:** OQ-01 to OQ-13, OQ-15, OQ-23, OQ-24 (16 questions still OPEN after Phase 14)
> **Status:** APPROVED 2026-10-29 (R1–R10 as recommended; see PROJECT_PROVENANCE_LOG.md) — Phase 15A IMPLEMENTATION IN PROGRESS
> **Date:** 2026-10-29
> **Baseline:** `main` = `phase-14-open-questions-locked` (`2f7a71f`)
> **Proposed Branch:** `phase15`

---

## 1. Method

For each question, the written "current assumption" was compared with **what the code does today**, checked in the code itself rather than taken from the docs. Each question falls into one of three groups:

- **Matches:** the code follows the assumption. Deciding only means confirming it, with no code change.
- **Diverges:** the code does something else. The decision says which one is right, and the other is changed.
- **Not implemented:** the assumption describes behaviour that does not exist yet.

---

## 2. Summary

| Group | OQ |
|---|---|
| **Diverges or not implemented** (needs a decision, then code) | **OQ-02** (no login rate limit at all), **OQ-05** (an admin can change their own role), **OQ-10** (PUBLIC problems open to every student, contrary to REQ-PROB-003), **OQ-01** (exam: several ACTIVE sessions per problem; practice: abandoned sessions stay ACTIVE forever, which also concerns OQ-13) |
| **Matches** (confirm only) | OQ-04, OQ-06, OQ-07, OQ-08, OQ-09, OQ-11, OQ-15, OQ-23 |
| **Product choice, no code needed if the current behaviour is kept** | OQ-03, OQ-12, OQ-13 (server side), OQ-24 |

---

## 3. Detail

### 3.1 Diverges — security and integrity

**OQ-02 — Login rate limiting** (Security Stakeholder)
- *Assumption:* temporary rate limit, no automatic lockout.
- *Code:* **nothing.** Failed logins are audited (REQ-AUTH-003) but never throttled. Passwords can be brute-forced without limit.
- *Options:* (a) per username + IP: 5 failures in 15 min → 429 `LOGIN_RATE_LIMITED` for 15 min, counter in Redis, no account lockout; (b) lock the account after N failures (an attacker can then lock out real users); (c) keep nothing.
- **Recommendation: (a).** Matches the assumption and avoids lockout-based denial of service. Small code change, plus tests.

**OQ-05 — Admin changes their own role** (Product Owner)
- *Assumption:* not allowed.
- *Code:* **allowed.** `PATCH /admin/users/{id}` has no `actor == target` check; only the last-admin rule (OQ-04) applies.
- *Options:* (a) forbid self role change **and** self lock (403 `SELF_MODIFICATION_FORBIDDEN`); another admin must do it; (b) allow (current).
- **Recommendation: (a).** Prevents an accidental self-demotion and keeps every privilege change a two-person action in the audit log.

**OQ-10 — Who may see PUBLIC problems** (Product Owner)
- *Assumption:* students enrolled in at least one class. This is also **REQ-PROB-003's acceptance criterion (MUST)**, domain §1 and the RBAC matrix ("STUDENT must be enrolled in at least one class").
- *Code:* **every student**, enrolled or not (problem read, practice start, public bank, practice list).
- *Options:* (a) follow REQ-PROB-003: a student with no active membership gets 403 `PROBLEM_FORBIDDEN` on PUBLIC problems and an empty public bank; (b) change the requirement to "every student" (needs a DCR on REQ-PROB-003).
- **Recommendation: (a).** The code is the one that is wrong; three authoritative documents agree.

### 3.2 Diverges — sessions

**OQ-01 — Practice: new session or resume? Exam: same session?** (Product Owner)
- *Assumption:* practice: every open = new session; exam: always the same session.
- *Code:*
  - Practice: every open creates a new session (matches), and nothing ever ends an abandoned one. A student who closes the tab leaves an ACTIVE session forever (`abandon_session` exists but nothing calls it, docs/34 §3.2).
  - Exam: every "start session" creates a **new** ACTIVE session, even while another ACTIVE one exists for the same problem. A student can split one exam problem's trace across several open sessions. Note that "always the same session" no longer fits D2 (Phase 10): submit ends the session and the next attempt opens a new one.
- *Options for the exam:* (a) at most one ACTIVE exam session per participation and problem; "start" returns the existing ACTIVE one (resume), and a new one opens only after submit/end; (b) keep several.
- *Options for practice:* (a) keep "new session per open", plus a stale-session policy: a practice session with no trace activity for `SESSION_STALE_HOURS` (default 24) is ended as ABANDONED (`SYSTEM_SESSION_POLICY`, existing finalization path); (b) resume the existing ACTIVE session for the same problem; (c) keep as is.
- **Recommendation: exam (a), practice (a).** One open exam session per problem keeps the evidence in one timeline. The stale policy closes the dangling sessions without changing what students see. Exam sessions are already closed by the timeout path.

**OQ-13 — Recovery after disconnect** (Tech Lead)
- *Assumption:* client buffers and retries; server inserts batches idempotently.
- *Code:* the server side exists and is tested: `(session_id, sequence_number)` idempotency, exact-duplicate retries accepted, conflicting duplicates → 409, `trace-state` for resync. The client side belongs to the frontend.
- **Recommendation:** resolve as written, with two additions:
  - The frontend contract is: buffer locally, resend with the same sequence numbers, and resync from `trace-state` after a reconnect.
  - Server-side abandonment is the stale policy in OQ-01.

### 3.3 Matches — confirm

| OQ | Question | Behaviour today (verified) | Recommendation |
|---|---|---|---|
| OQ-04 | Lock or demote the last ADMIN? | Refused with 400 `LAST_ADMIN_PROTECTED`, under a row lock | Confirm |
| OQ-06 | Configurable thresholds besides idle? | Only `idle_threshold_minutes` is admin-configurable (Phase 13); others are deployment settings; LOC uses a relative threshold | Confirm |
| OQ-07 | Duplicate class names per teacher? | Allowed (no unique constraint); classes are told apart by id and invite code | Confirm |
| OQ-08 | Teacher approval for enrollment? | Auto-approved on `POST /my/classes/join` (Phase 12) | Confirm |
| OQ-09 | Problem without test cases saved as draft? | Allowed; exam publish requires ≥1 test case per problem (Phase 10B); submit → 422 | Confirm |
| OQ-11 | DRAFT exam with no problem? | Saved; publish → 422 `EXAM_NO_PROBLEM` | Confirm |
| OQ-15 | Who sees submission results? | docs/36 D14: practice always; exam after ENDED + `allow_view_result_after` | Confirm |
| OQ-23 | ADMIN cancels an ONGOING exam? | Refused with 409 `EXAM_ONGOING_CANCEL_UNDECIDED` (docs/36 D13) | Confirm "not in V1" (error code renamed to `EXAM_ONGOING_CANCEL_FORBIDDEN` once decided) |

### 3.4 Product choices

**OQ-03 — Email on account creation:** no mail infrastructure exists; the admin hands over a temporary password and the user must change it at first login.
- **Recommendation:** OUT_OF_SCOPE for V1, like OQ-25.

**OQ-12 — Assignments outside exams:** today a teacher publishes a CLASS problem to a class (Phase 05), and students find it in `GET /my/practice/problems` (Phase 13). There are no due dates.
- *Options:* (a) publication = assignment, no deadline in V1; (b) add an assignment entity with a due date (new feature, new spec).
- **Recommendation: (a)** for V1.

**OQ-24 — Reuse of another teacher's PUBLIC problem:** today a teacher can **read** another teacher's PUBLIC problem statement, but cannot see its test cases, attach it to an exam, publish it or copy it.
- *Options:* (a) read-only (current); (b) "copy to my bank": new problem owned by the copier, statement and **sample** test cases only (hidden tests stay the author's); (c) attach directly.
- **Recommendation: (a)** for V1. (b) is a reasonable later feature.

---

## 4. Decisions Requested

| ID | OQ | Recommendation | Code work if accepted |
|---|---|---|---|
| R1 | OQ-02 | (a) 5 failures / 15 min per username+IP → 429, no lockout | Yes: Redis counter in login, tests |
| R2 | OQ-05 | (a) no self role change, no self lock | Yes: one check, tests |
| R3 | OQ-10 | (a) follow REQ-PROB-003: PUBLIC requires an active class membership | Yes: access checks, tests; updates Phase 05/13 tests that use unenrolled students |
| R4 | OQ-01 exam | (a) one ACTIVE exam session per participation+problem (resume) | Yes |
| R5 | OQ-01 practice / OQ-13 | (a) new session per open + stale policy (24 h without activity → ABANDONED) | Yes: scheduler sweep, tests |
| R6 | OQ-13 | Resolve as written + frontend contract | Docs |
| R7 | OQ-04, 06, 07, 08, 09, 11, 15, 23 | Confirm current behaviour | Docs (OQ-23: rename error code) |
| R8 | OQ-03 | OUT_OF_SCOPE V1 | Docs |
| R9 | OQ-12 | Publication = assignment, no deadline in V1 | Docs |
| R10 | OQ-24 | Read-only reuse in V1 | Docs |

If accepted, R1–R5 become a short Phase 15A (behaviour fixes, with tests and regression) to run before or alongside the CI work (Step 1). R6–R10 are recorded in `OPEN_QUESTIONS.md` and `PROJECT_PROVENANCE_LOG.md`; R3 and R7 record that the code now follows the requirement.
