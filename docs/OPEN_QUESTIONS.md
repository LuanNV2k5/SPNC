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

### OQ-01 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Session luyện tập — mỗi lần mở bài là Session mới hay resume Session cũ?
**Why it matters:** Session model, working_time logic, TEACHER timeline.
**Options:** (1) New session mỗi lần mở; (2) Resume nếu trong N phút; (3) User chọn.
**Current assumption:** Option 1 — each open = new Session. In Exam: always same Session.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-02 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Login rate limiting — ngưỡng và behavior?
**Why it matters:** Auth module, brute-force protection.
**Options:** (1) 5 lần sai → 15 phút rate limit; (2) Lockout account.
**Current assumption:** Rate limit tạm thời, không auto-lockout.
**Owner:** Security Stakeholder | **Status:** OPEN

---

### OQ-03 — OPEN | NON_BLOCKING_V1

**Question:** Email notification khi tạo tài khoản — bắt buộc hay optional?
**Current assumption:** Optional trong V1.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-04 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Có cho phép khóa ADMIN duy nhất còn lại không?
**Current assumption:** Không cho phép.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-05 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** ADMIN có thể đổi role của chính mình không?
**Current assumption:** Không cho phép tự đổi.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-06 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Danh sách đầy đủ threshold có thể cấu hình ngoài idle_threshold_minutes?
**Current assumption:** Chỉ idle_threshold_minutes trong V1. LOC anomaly không có absolute threshold.
**Owner:** Product Owner | **Status:** OPEN

---

## Class Management

### OQ-07 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Có cho phép trùng tên lớp của cùng một TEACHER không?
**Current assumption:** Cho phép (unique theo id).
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-08 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Enrollment có cần TEACHER duyệt không?
**Current assumption:** Tự động approved.
**Owner:** Product Owner | **Status:** OPEN

---

## Problem Management

### OQ-09 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Problem không có test case — cho lưu draft?
**Current assumption:** Cho lưu draft; validate khi publish.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-10 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Problem visibility PUBLIC — mọi STUDENT enrolled hay mọi STUDENT?
**Current assumption:** Mọi STUDENT enrolled ít nhất 1 lớp.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-11 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Exam DRAFT không có problem — save được không?
**Current assumption:** Save DRAFT; không publish nếu 0 problem.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-12 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Assignment (gán bài ngoài kỳ thi) — flow chi tiết?
**Current assumption:** Chưa đủ thông tin; SHOULD trong backlog.
**Owner:** Product Owner | **Status:** OPEN

---

## Coding & Trace

### OQ-13 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Session recovery khi STUDENT disconnect — cơ chế cụ thể?
**Current assumption:** Client buffer + retry; server idempotent batch insert.
**Owner:** Tech Lead | **Status:** OPEN

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

### OQ-15 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Permission xem lịch sử submission của STUDENT — ai cấp, điều kiện?
**Current assumption:** Mặc định cho xem ngoài kỳ thi; trong kỳ thi xem sau Exam ENDED + allow_view_result_after=true.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-16 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Cơ chế tích điểm — dùng để làm gì, reset thế nào?
**Current assumption:** Chưa đủ thông tin; SHOULD trong backlog.
**Owner:** Product Owner | **Status:** OPEN

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

### OQ-23 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Admin emergency exam cancellation — ADMIN có cancel Exam ONGOING không?
**Current assumption:** ADMIN không cancel ONGOING trong V1. Xem NG12.
**Owner:** Product Owner | **Status:** OPEN

---

### OQ-24 — OPEN | BLOCKING_IMPLEMENTATION

**Question:** Cross-teacher PUBLIC problem reuse/copy?
**Current assumption:** Chưa xác định.
**Owner:** Product Owner | **Status:** OPEN

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

---

## Summary: Remaining Open Questions by Phase

| Phase Blocked | OQ-IDs |
|---------------|--------|
| BLOCKING_IMPLEMENTATION | OQ-01, 02, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 15, 16, 23, 24 |
| NON_BLOCKING_V1 | OQ-03 |
| BLOCKING_ARCHITECTURE | **None remaining** ✓ |
