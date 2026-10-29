# OPEN QUESTIONS

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline
> **Date:** 2026-09-19
> **Status:** 7 BLOCKING_ARCHITECTURE RESOLVED; remaining OPEN questions are BLOCKING_IMPLEMENTATION (non-blocking for Architecture)

---

## Format

Mỗi OQ gồm:
- **OQ-ID / Status / Blocking phase**
- **Question, Why it matters, Options, Assumption**
- Nếu RESOLVED: **Decision, Reason, Affected Requirements**

---

## Authentication & User Management

### OQ-01 — RESOLVED (2026-10-29, docs/41 R4, R5)

**Question:** Session luyện tập — mỗi lần mở bài là Session mới hay resume Session cũ?
**Why it matters:** Session model, working_time logic, TEACHER timeline.
**Options:** (1) New session mỗi lần mở; (2) Resume nếu trong N phút; (3) User chọn.
**Decision:** Practice: each open creates a new session; a practice session with no trace activity for SESSION_STALE_HOURS (24) is ended as ABANDONED (SYSTEM_SESSION_POLICY). Exam: at most one ACTIVE session per participation and problem; starting again resumes it; a new one opens only after submit/end (docs/36 D2).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-02 — RESOLVED (2026-10-29, docs/41 R1)

**Question:** Login rate limiting — ngưỡng và behavior?
**Why it matters:** Auth module, brute-force protection.
**Options:** (1) 5 lần sai → 15 phút rate limit; (2) Lockout account.
**Decision:** Per username + client IP: 5 failed logins within 15 minutes → 429 LOGIN_RATE_LIMITED for 15 minutes; no account lockout; a successful login resets the counter.
**Owner:** Security Stakeholder | **Status:** RESOLVED

---

### OQ-03 — RESOLVED (2026-10-29, docs/41 R8)

**Question:** Email notification khi tạo tài khoản — bắt buộc hay optional?
**Decision:** OUT_OF_SCOPE V1. The admin hands over a temporary password; the user must change it at first login.
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-04 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Có cho phép khóa ADMIN duy nhất còn lại không?
**Decision:** Confirmed: the last usable ADMIN cannot be locked or demoted (400 LAST_ADMIN_PROTECTED).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-05 — RESOLVED (2026-10-29, docs/41 R2)

**Question:** ADMIN có thể đổi role của chính mình không?
**Decision:** An ADMIN cannot change their own role or status (403 SELF_MODIFICATION_FORBIDDEN); another admin must do it.
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-06 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Danh sách đầy đủ threshold có thể cấu hình ngoài idle_threshold_minutes?
**Decision:** Confirmed: only idle_threshold_minutes is admin-configurable in V1 (Phase 13); LOC anomaly stays relative.
**Owner:** Product Owner | **Status:** RESOLVED

---

## Class Management

### OQ-07 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Có cho phép trùng tên lớp của cùng một TEACHER không?
**Decision:** Confirmed: duplicate class names per teacher are allowed.
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-08 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Enrollment có cần TEACHER duyệt không?
**Decision:** Confirmed: enrollment by invite code is auto-approved.
**Owner:** Product Owner | **Status:** RESOLVED

---

## Problem Management

### OQ-09 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Problem không có test case — cho lưu draft?
**Decision:** Confirmed: a problem without test cases can be saved; exam publish requires test cases; submit is refused (422).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-10 — RESOLVED (2026-10-29, docs/41 R3)

**Question:** Problem visibility PUBLIC — mọi STUDENT enrolled hay mọi STUDENT?
**Decision:** PUBLIC problems are visible to students with at least one active class membership (REQ-PROB-003) and to all teachers.
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-11 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Exam DRAFT không có problem — save được không?
**Decision:** Confirmed: a DRAFT exam without problems can be saved; publish is refused (422).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-12 — RESOLVED (2026-10-29, docs/41 R9)

**Question:** Assignment (gán bài ngoài kỳ thi) — flow chi tiết?
**Decision:** V1: publishing a CLASS problem to a class is the assignment; no due date.
**Owner:** Product Owner | **Status:** RESOLVED

---

## Coding & Trace

### OQ-13 — RESOLVED (2026-10-29, docs/41 R6)

**Question:** Session recovery khi STUDENT disconnect — cơ chế cụ thể?
**Decision:** Server: idempotent batch ingest by (session_id, sequence_number) plus trace-state resync. Client contract (frontend): buffer locally, resend with the same sequence numbers, resync from trace-state after reconnect. Abandoned practice sessions are closed by the stale policy (OQ-01).
**Owner:** Tech Lead | **Status:** RESOLVED

---

### OQ-14 — **RESOLVED** | BLOCKING_ARCHITECTURE → RESOLVED

**Question:** TEACHER có thể xem trace real-time (live session) không?

**Decision:** V1 dùng REST + WebSocket hybrid.
- **REST API:** Initial dashboard data, historical timeline, session detail, run history, pagination/query.
- **WebSocket:** Lightweight realtime updates — session activity status, new Run result notification, new AttentionSignal notification, student/session state change.
- **KHÔNG** stream raw source code mỗi keystroke qua WebSocket.
- Raw/editor trace vẫn đi qua Trace Ingestion pipeline.
- Teacher mở detail/replay → REST API (lịch sử).
- WebSocket disconnect → client reconnect + REST refetch/resync.
- **Database/server state là source of truth.** WebSocket chỉ là notification channel.

**Reason:** Balance giữa real-time UX và infrastructure complexity; tránh WS becoming source of truth.

**Affected Requirements:** NFR-REL-002 (retry), REQ-OBS-003, REQ-OBS-008; New NFR-REALTIME-001/002/003 added.

**Owner:** Tech Lead | **Status:** RESOLVED

---

### OQ-15 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Permission xem lịch sử submission của STUDENT — ai cấp, điều kiện?
**Decision:** Confirmed: docs/36 D14 (practice always; exam after ENDED + allow_view_result_after).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-16 — RESOLVED (2026-10-29, docs/40 Q1–Q3)

**Question:** Cơ chế tích điểm — dùng để làm gì, reset thế nào?
**Decision:** Practice only; points once per problem at the first ACCEPTED submission (EASY 10, MEDIUM 20, HARD 30, no difficulty 10); cumulative, never reset; visible to the student and to teachers of their classes; no leaderboard. Exam submissions never award points.
**Owner:** Product Owner | **Status:** RESOLVED

---

## Non-Functional

### OQ-17 — **RESOLVED** | BLOCKING_ARCHITECTURE → RESOLVED

**Question:** Số lượng concurrent sessions tối đa cần hỗ trợ?

**Decision:**
- **EXPECTED_BASELINE = 500** concurrent active coding sessions.
- **LOAD_TEST_TARGET = 1,000** concurrent simulated sessions.
- Đây là engineering capacity target, KHÔNG phải hard business limit.
- Không hardcode MAX_STUDENTS = 500 vào business logic.
- Architecture phải cho phép horizontal scaling trong tương lai.

**Reason:** Cung cấp con số cụ thể để size infrastructure mà không tạo artificial limit.

**Affected Requirements:** NFR-PERF-006 (updated), NFR-SCALE-001/002.

**Owner:** Stakeholder | **Status:** RESOLVED

---

### OQ-18 — **RESOLVED** | BLOCKING_ARCHITECTURE → RESOLVED

**Question:** Volume trace events ước tính per session?

**Decision:**
- **Capacity planning baseline:** Architecture phải xử lý được ~20,000 trace events per session dài.
- Đây là sizing assumption, KHÔNG phải giới hạn nghiệp vụ.
- Không reject session chỉ vì vượt 20,000 events.
- Trace ingest: batch, idempotent, retry, preserve ordering, tránh 1 HTTP request per keystroke.
- Physical partitioning/DB optimization quyết định trong Architecture/Database phase sau benchmark.

**Reason:** Cung cấp basis cho storage sizing mà không over-engineer premature partitioning.

**Affected Requirements:** NFR-SCALE-003 (updated), NFR-PERF-007, REQ-TRACE-010.

**Owner:** Tech Lead | **Status:** RESOLVED

---

### OQ-19 — **RESOLVED** | BLOCKING_ARCHITECTURE → RESOLVED

**Question:** SLA uptime cụ thể?

**Decision:**
- **V1 deployment target: 99.5% monthly availability.**
- Đây là deployment target, không phải safety-critical SLA.
- Architecture phải có: health checks, graceful restart, retry hợp lý, Judge isolation, DB backup.
- Không bắt buộc multi-region, active-active, hoặc enterprise HA trong V1.

**Reason:** Reasonable target cho educational platform V1 mà không over-engineer.

**Affected Requirements:** NFR-REL-001 (updated).

**Owner:** Stakeholder | **Status:** RESOLVED

---

### OQ-20 — **RESOLVED** | BLOCKING_ARCHITECTURE → RESOLVED

**Question:** Backup strategy — tần suất, RPO, RTO?

**Decision:**
- **RPO ≤ 24 hours.**
- **RTO ≤ 4 hours.**
- Phải backup: PostgreSQL database + persistent snapshot/object metadata.
- Architecture cho phép nâng cấp backup policy sau này.
- Không hardcode retention backup vào domain logic.

**Reason:** V1 baseline phù hợp với educational platform; upgrade path rõ ràng.

**Affected Requirements:** NFR-REL-004 (updated), new NFR-REL-007.

**Owner:** Stakeholder | **Status:** RESOLVED

---

### OQ-21 — **RESOLVED** | BLOCKING_ARCHITECTURE → RESOLVED

**Question:** Data privacy policy cho trace data — retention, GDPR?

**Decision:**
- V1 áp dụng: data minimization, least privilege, audit access, configurable retention.
- **Default retention baseline: Raw detailed trace = 180 days.**
- Aggregated academic/submission records: theo policy của đơn vị triển khai.
- **Retention MUST configurable.** 180 days KHÔNG hardcode trong business logic.
- Deletion/retention process phải giữ referential integrity.
- Nếu deployment thực tế có legal requirement khác: deployment policy override baseline.
- **"V1 privacy engineering baseline — not a certification of GDPR compliance."**

**Reason:** Cung cấp reasonable default mà không tuyên bố compliance chưa được legal review.

**Affected Requirements:** NFR-ETH-006, new NFR-DATA-008.

**Owner:** Legal / Stakeholder | **Status:** RESOLVED

---

### OQ-22 — **RESOLVED** | BLOCKING_ARCHITECTURE → RESOLVED

**Question:** Ngôn ngữ lập trình được hỗ trợ trong code runner?

**Decision:**
- **V1 Judge chính thức hỗ trợ:**
  1. `CPP17` — GCC-compatible compiler, C++17 standard.
  2. `PYTHON3` — Python 3.x runtime.
- Language identifiers canonical: `CPP17`, `PYTHON3` (all caps, no spaces).
- Version cụ thể của compiler/runtime là deployment configuration.
- Judge architecture phải extensible để thêm language adapter sau này.
- Không implement Java, JavaScript, hoặc ngôn ngữ khác trong V1.

**Reason:** Giới hạn V1 scope để tập trung sandbox engineering cho 2 ngôn ngữ phổ biến nhất.

**Affected Requirements:** New REQ-RUN-005, Problem.language_allowed domain update.

**Owner:** Product Owner | **Status:** RESOLVED

---

## New Questions Added in v0.2 Remediation

### OQ-23 — RESOLVED (2026-10-29, docs/41 R7)

**Question:** Admin emergency exam cancellation — ADMIN có cancel Exam ONGOING không?
**Decision:** ADMIN does not cancel ONGOING exams in V1 (409 EXAM_ONGOING_CANCEL_FORBIDDEN).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-24 — RESOLVED (2026-10-29, docs/41 R10)

**Question:** Cross-teacher PUBLIC problem reuse/copy?
**Decision:** V1: teachers may read other teachers' PUBLIC problem statements only (no test cases, no copy, no attach).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-26 — RESOLVED (2026-10-29, docs/40 Q4)

**Question:** Production isolation of the judge zone (docs/10 §2): how does the judge worker reach a container runtime without host-root-equivalent access (rootless Docker, dedicated judge host/VM, gVisor/Kata, remote Docker over TLS)?
**Decision:** Production judge workers run on a dedicated judge host (VM) with its own Docker daemon; the core zone exposes no container runtime; sandbox containers use the gVisor runtime (`runsc`, setting `JUDGE_CONTAINER_RUNTIME`); the worker uses a least-privilege PostgreSQL role. The socket-mount compose stack stays demo/dev only.
**Owner:** Tech Lead / Security Stakeholder | **Status:** RESOLVED

---

### OQ-27 — RESOLVED (2026-10-29, docs/40 Q5)

**Question:** What does `Exam.duration_minutes` mean (REQ-EXAM-001; not defined in docs 01–03)?
**Decision:** Optional per-student limit; deadline = `min(participation.started_at + duration_minutes, end_time)`; null = no per-student limit. (confirms docs/38 D7).
**Owner:** Product Owner | **Status:** RESOLVED

---

### OQ-25 — OUT_OF_SCOPE (V1)

**Question:** Forgot password / self-service password recovery?
**Decision:** ADMIN reset thủ công trong V1. Self-service = OUT_OF_SCOPE V1. Xem NG11.
**Status:** OUT_OF_SCOPE

---

## Resolved Questions (Reference)

| OQ-ID | Topic | Status |
|-------|-------|--------|
| OQ-R01 | Student raw trace viewer | RESOLVED — OUT_OF_SCOPE V1 |
| OQ-14 | Live teacher trace view | RESOLVED — REST + WebSocket hybrid |
| OQ-17 | Concurrent sessions | RESOLVED — 500 baseline / 1000 load-test |
| OQ-18 | Trace event volume | RESOLVED — 20,000 events/session capacity |
| OQ-19 | SLA uptime | RESOLVED — 99.5% monthly |
| OQ-20 | Backup RPO/RTO | RESOLVED — RPO 24h / RTO 4h |
| OQ-21 | Data privacy baseline | RESOLVED — 180 days configurable, non-GDPR-certified |
| OQ-22 | Supported languages | RESOLVED — CPP17, PYTHON3 |
| OQ-25 | Forgot password | RESOLVED — OUT_OF_SCOPE V1 |
| OQ-16 | Points mechanism | RESOLVED — practice-only, once per problem, by difficulty, no leaderboard (docs/40) |
| OQ-26 | Production judge isolation | RESOLVED — dedicated judge VM + gVisor + least-privilege DB role (docs/40) |
| OQ-27 | `duration_minutes` meaning | RESOLVED — min(started_at + duration, end_time) (docs/40) |
| OQ-01 | Practice: each open creates a new session; a practice session with no trace acti | RESOLVED (docs/41) |
| OQ-02 | Per username + client IP: 5 failed logins within 15 minutes → 429 LOGIN_RATE_LIM | RESOLVED (docs/41) |
| OQ-03 | OUT_OF_SCOPE V1 | RESOLVED (docs/41) |
| OQ-04 | Confirmed: the last usable ADMIN cannot be locked or demoted (400 LAST_ADMIN_PRO | RESOLVED (docs/41) |
| OQ-05 | An ADMIN cannot change their own role or status (403 SELF_MODIFICATION_FORBIDDEN | RESOLVED (docs/41) |
| OQ-06 | Confirmed: only idle_threshold_minutes is admin-configurable in V1 (Phase 13); L | RESOLVED (docs/41) |
| OQ-07 | Confirmed: duplicate class names per teacher are allowed | RESOLVED (docs/41) |
| OQ-08 | Confirmed: enrollment by invite code is auto-approved | RESOLVED (docs/41) |
| OQ-09 | Confirmed: a problem without test cases can be saved; exam publish requires test | RESOLVED (docs/41) |
| OQ-10 | PUBLIC problems are visible to students with at least one active class membershi | RESOLVED (docs/41) |
| OQ-11 | Confirmed: a DRAFT exam without problems can be saved; publish is refused (422) | RESOLVED (docs/41) |
| OQ-12 | V1: publishing a CLASS problem to a class is the assignment; no due date | RESOLVED (docs/41) |
| OQ-13 | Server: idempotent batch ingest by (session_id, sequence_number) plus trace-stat | RESOLVED (docs/41) |
| OQ-15 | Confirmed: docs/36 D14 (practice always; exam after ENDED + allow_view_result_af | RESOLVED (docs/41) |
| OQ-23 | ADMIN does not cancel ONGOING exams in V1 (409 EXAM_ONGOING_CANCEL_FORBIDDEN) | RESOLVED (docs/41) |
| OQ-24 | V1: teachers may read other teachers' PUBLIC problem statements only (no test ca | RESOLVED (docs/41) |

---

## Summary: Remaining Open Questions by Phase

| Phase Blocked | OQ-IDs |
|---------------|--------|
| BLOCKING_IMPLEMENTATION | **None remaining** ✓ |
| BLOCKING_ARCHITECTURE | **None remaining** ✓ |
