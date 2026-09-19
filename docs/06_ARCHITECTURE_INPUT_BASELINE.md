# 06 — ARCHITECTURE INPUT BASELINE

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline
> **Date:** 2026-09-19
> **Status:** FINALIZED (Input for Phase 01)

---

## Mục đích tài liệu

Tài liệu này tổng hợp các ràng buộc nghiệp vụ (Business Constraints), giới hạn hệ thống (System Baselines), và các quyết định kiến trúc đã được Stakeholder chốt (Approved Decisions) từ Phase 00.

**ĐÂY LÀ ĐẦU VÀO CHO PHASE 01 (ARCHITECTURE DESIGN).**
Kiến trúc sư hệ thống (System Architect) PHẢI tuân thủ tuyệt đối các ràng buộc trong tài liệu này khi thiết kế Database, API, và Deployment Topology.
**KHÔNG thiết kế Architecture chi tiết trong file này.**

---

## 1. User Roles

Hệ thống có 3 role chính:
1. **ADMIN:** Quản trị viên hệ thống. Quản lý tài khoản, cấu hình hệ thống, xem system-wide read-only (không sửa nội dung học thuật).
2. **TEACHER:** Giáo viên. Tạo/quản lý lớp, đề bài, kỳ thi, xem và đánh giá trace của học sinh trong lớp mình.
3. **STUDENT:** Học sinh. Tham gia lớp, luyện tập, làm bài thi, sinh ra digital trace. Không được xem raw trace.

---

## 2. Core Modules

1. **AUTH & USER:** Đăng nhập, đăng xuất, đổi mật khẩu, phân quyền.
2. **CLASS:** Quản lý lớp, học sinh.
3. **PROBLEM:** Kho đề, tạo và chỉnh sửa đề bài, test cases.
4. **EXAM:** Tạo, publish, tham gia kỳ thi.
5. **TRACE & SESSION:** Thu thập trace event (append-only), quản lý session.
6. **OBSERVATION & SIGNAL:** Teacher timeline, annotation, attention signals (tự động, không phán xét).
7. **RUN & JUDGE:** Thực thi code trong sandbox, chấm điểm.
8. **STUDENT HISTORY:** Xem kết quả submission.

---

## 3. Supported Languages (OQ-22)

**V1 Judge chính thức hỗ trợ:**
- `CPP17` — C++17 (GCC-compatible).
- `PYTHON3` — Python 3.x.
*(Không implement ngôn ngữ khác trong V1. Kiến trúc Judge phải extensible cho tương lai).*

---

## 4. Expected Concurrency & Capacity (OQ-17, OQ-18)

- **Expected Active Sessions:** `500` concurrent coding sessions.
- **Load-Test Target:** `1,000` concurrent simulated sessions.
  *(Đây là engineering capacity target, không phải hard limit của business).*
- **Trace Volume Assumption:** ~`20,000` trace events per session dài.
  *(Hệ thống phải chịu tải tốt, hỗ trợ batch ingestion, idempotent retries).*

---

## 5. Realtime Requirement (OQ-14)

- **Mô hình Hybrid (REST + WebSocket):**
  - **REST API:** Nguồn dữ liệu chính (initial load, historical data).
  - **WebSocket:** Chỉ dùng để notification (status updates, signal alerts).
- **KHÔNG stream raw source code** mỗi keystroke tới Teacher qua WebSocket.
- Database/Server State luôn là **Source of Truth**. Client phải refetch REST khi WS reconnect.

---

## 6. Availability & Backup (OQ-19, OQ-20)

- **Availability Target:** `99.5%` monthly uptime (không bắt buộc multi-region V1).
- **RPO (Recovery Point Objective):** `<= 24 hours`.
- **RTO (Recovery Time Objective):** `<= 4 hours`.
- **Backup Target:** PostgreSQL database và persistent object storage (metadata).

---

## 7. Privacy & Retention Baseline (OQ-21)

- **Retention (Raw Trace):** Default `180 days` (phải là giá trị cấu hình, không hardcode trong logic).
- V1 áp dụng Data Minimization, Least Privilege, Audit Logging.
- **Không tuyên bố GDPR compliant** nếu chưa qua legal review.

---

## 8. Judge Isolation Requirement

- Code của học sinh **tuyệt đối KHÔNG** chạy trong API process.
- Code Runner phải là sandbox riêng biệt.
- Giới hạn Sandbox: CPU, RAM, Time, Network (chặn external access), Filesystem (chỉ /tmpdir).

---

## 9. Trace Invariants

- Mọi Trace Event là **APPEND-ONLY**. Không Update, không Delete.
- Trace ingestion hỗ trợ **BATCH** và **IDEMPOTENT** (dựa trên `session_id` + `sequence_number`).
- `sequence_number` là positive integer (1-based), duy nhất per session.
- Client_timestamp được lưu tham chiếu. **Server_timestamp là Authoritative.**
- CodeSnapshot là **IMMUTABLE** khi được tạo (Run/Submit/Checkpoint).

---

## 10. Session & Exam Lifecycle Invariants

- **Exam Timeout:** Bắt buộc **SERVER-SIDE enforcement** (không phụ thuộc client).
  - Scheduler/status materialization có tolerance `<= 60 seconds`.
  - Tuy nhiên, **Authorization API phải dùng time-window chính xác** trực tiếp (không dùng materialized status để bypass authorization).
- **Session ABANDONED:**
  - Chỉ áp dụng cho Practice session bị bỏ dở (configurable stale policy).
  - **KHÔNG** áp dụng cho Exam timeout (dùng ENDED + SYSTEM_EXAM_TIMEOUT).
  - **KHÔNG** đánh dấu ABANDONED chỉ vì IDLE >= threshold (idle chỉ sinh IDLE_DETECTED signal).
- **Practice + Exam Concurrency:**
  - Học sinh **KHÔNG ĐƯỢC** bắt đầu Practice Session khi đang có ExamParticipation = IN_PROGRESS.

---

## 11. RBAC Invariants

- **Backend Enforcement:** Mọi check phân quyền phải chạy dưới backend.
- **TEACHER Isolation:** Giáo viên chỉ truy cập (Read/Update/Observe) học sinh và kỳ thi thuộc **lớp do mình làm owner**.
- **STUDENT Isolation:** Học sinh chỉ truy cập dữ liệu của chính mình.
- **Raw Trace Privacy (V1):** Học sinh **DENY** đối với raw trace viewer.

---

## 12. Ethical Constraints

- **Hệ thống KHÔNG kết luận tự động:** "Gian lận", "Không hiểu bài", "Yếu".
- **Attention Signal:** Chỉ báo cáo **hiện tượng quan sát được** (IDLE_DETECTED, LOC_ANOMALY, REPEATED_FAILURE, FAST_FIRST_CODE).
- **Evidence Factual:** Mọi signal phải kèm evidence JSON (timestamp, count, delta), không có wording phán xét.
- **Giáo viên là người diễn giải duy nhất.**

---

## 13. Unresolved Non-Blocking Questions

Các câu hỏi chưa giải quyết (xem `OPEN_QUESTIONS.md`) chủ yếu ở mức **BLOCKING_IMPLEMENTATION**.
Chúng **KHÔNG BLOCK ARCHITECTURE**.
Architect có thể tự tin bắt đầu thiết kế hệ thống mà không cần chờ:
- `OQ-01` (Session resume vs new)
- `OQ-02` (Login rate limit)
- `OQ-06` (Other config thresholds)
- `OQ-13` (Disconnect buffer size)
- `OQ-23` (Emergency cancel EXAM)
- v.v. (Xem OPEN_QUESTIONS.md)
