# 00 — SCOPE

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline
> **Date:** 2026-09-19
> **Status:** DRAFT — Phase 00 Baseline

---

## 1. Vision

Xây dựng một nền tảng học lập trình trực tuyến có khả năng **thu thập dấu vết số (digital trace)** của quá trình làm bài của học sinh, cho phép giáo viên quan sát hành trình tư duy — không phải chỉ kết quả cuối cùng.

Hệ thống **không** thay thế phán đoán của giáo viên. Hệ thống là **công cụ quan sát**, cung cấp bằng chứng để giáo viên diễn giải.

---

## 2. Goals

| # | Goal | Mức độ |
|---|------|--------|
| G1 | Cho phép giáo viên tạo và quản lý bài tập lập trình | MUST |
| G2 | Cho phép học sinh làm bài trong môi trường code online | MUST |
| G3 | Thu thập dấu vết số trong suốt quá trình làm bài | MUST |
| G4 | Trình bày dấu vết dưới dạng timeline có thể đọc được | MUST |
| G5 | Sinh attention signal khi có dấu hiệu bất thường, có bằng chứng | MUST |
| G6 | Quản trị hệ thống bởi ADMIN | MUST |
| G7 | Tổ chức kỳ thi với kiểm soát truy cập | MUST |
| G8 | Hệ thống tích điểm cho học sinh | SHOULD |
| G9 | Phân tích thống kê lớp học | SHOULD |

---

## 3. Non-Goals (Out-of-Scope)

| # | Điều KHÔNG thuộc phạm vi |
|---|--------------------------|
| NG1 | Tự động kết luận học sinh gian lận |
| NG2 | Tự động kết luận học sinh không hiểu bài |
| NG3 | AI/ML tự chấm điểm chủ quan |
| NG4 | Hệ thống video call / livestream |
| NG5 | Mobile native app (iOS/Android) — V1 |
| NG6 | Plagiarism detection engine (chỉ là attention signal, không phán xét) |
| NG7 | LMS tổng hợp (quản lý giáo trình, học liệu phi lập trình) |
| NG8 | Thanh toán / subscription |
| NG9 | Tích hợp với hệ thống trường học bên ngoài (ERP, SIS) — V1 |
| NG10 | **Student raw trace viewer** — STUDENT không xem raw digital trace, editor timeline, attention signal hoặc code replay của chính mình trong V1. Digital Trace Observation là chức năng dành riêng cho TEACHER. |
| NG11 | **Forgot password qua email** — V1 không có self-service password recovery. ADMIN reset mật khẩu thủ công. |
| NG12 | **Admin emergency exam cancellation** — Chưa được stakeholder quyết định. Xem OQ-23. |

---

## 4. Actors

| Actor | Mô tả |
|-------|--------|
| **ADMIN** | Quản trị viên hệ thống. Có quyền cao nhất. Không nhất thiết là giáo viên. |
| **TEACHER** | Giáo viên/Giảng viên. Tạo và quản lý lớp, đề bài, kỳ thi. Đọc dấu vết. |
| **STUDENT** | Học sinh. Làm bài, luyện tập, dự thi. Sinh ra dấu vết số. |
| **System** | Tác nhân nội bộ: scheduler, code runner, signal engine. Không phải người dùng. |

---

## 5. System Boundaries

```
+------------------------------------------------------------------+
|                   DTPLS System Boundary                          |
|                                                                  |
|  +----------+   +--------------+   +------------------------+   |
|  |  Admin   |   |   Teacher    |   |       Student          |   |
|  |  Portal  |   |   Portal     |   |     Code Editor        |   |
|  +-----+----+   +------+-------+   +-----------+------------+   |
|        |               |                       |                |
|  +-----v---------------v-----------------------v-----------+    |
|  |                    API Gateway / Backend                 |    |
|  |   Auth · User Mgmt · Class · Problem · Exam · Trace     |    |
|  +-----------------------------+----------------------------+    |
|                                |                                 |
|  +-----------------------------v----------------------------+    |
|  |  Database Layer  |  Trace Store  |  Signal Engine        |    |
|  +----------------------------------------------------------+    |
|                                |                                 |
|  +-----------------------------v----------------------------+    |
|  |              Code Runner (Isolated Sandbox)              |    |
|  +----------------------------------------------------------+    |
+------------------------------------------------------------------+

External:
  - Email provider (notifications)
  - OAuth provider (optional SSO)
```

---

## 6. Key Constraints

| Constraint | Nguồn |
|-----------|-------|
| Code học sinh KHÔNG chạy trong API process | PROJECT_RULES #18 |
| Code runner phải sandbox CPU/RAM/time/filesystem/network | PROJECT_RULES #19 |
| Trace event là append-only | PROJECT_RULES #14 |
| Timestamp dùng UTC tại database | PROJECT_RULES #15 |
| Client timestamp được ghi nhận nhưng không tin tuyệt đối | PROJECT_RULES #17 |
| Hệ thống KHÔNG kết luận gian lận/yếu/không hiểu | PROJECT_RULES #20–22 |
| Authorization phải enforce tại backend | PROJECT_RULES #9 |
| TEACHER chỉ truy cập lớp/học sinh của mình | PROJECT_RULES #12 |
| STUDENT chỉ chỉnh sửa dữ liệu của chính mình | PROJECT_RULES #13 |

---

## 7. Phân loại ưu tiên (MoSCoW)

| Ký hiệu | Ý nghĩa |
|---------|---------|
| **MUST** | Bắt buộc. Thiếu = hệ thống không hoạt động được. |
| **SHOULD** | Quan trọng. Nên có trong release 1. |
| **COULD** | Tốt nếu có. Có thể trì hoãn. |
| **OUT-OF-SCOPE** | Không phát triển trong phạm vi này. |

---

## 8. Phạm vi phân tích hiện tại

Tài liệu này và các tài liệu đi kèm (`01–06`) **CHỈ** là phân tích yêu cầu.  
**Chưa có thiết kế kỹ thuật, chưa có code, chưa có schema database.**

Mọi câu hỏi chưa rõ được đưa vào [`OPEN_QUESTIONS.md`](./OPEN_QUESTIONS.md).

---

## 9. Lịch sử thay đổi

| Version | Date | Thay đổi |
|---------|------|----------|
| 0.1 | 2026-09-19 | Khởi tạo |
| 0.2 | 2026-09-19 | Remediation QA Round 1: G7 MUST; bổ sung NG10/NG11/NG12 |
| 0.3 | 2026-09-19 | Final Phase 00 Baseline |
