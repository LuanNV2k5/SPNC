# ANALYSIS REPORT — Digital Trace Programming Learning System

> **Vai trò:** Principal Software Architect / Senior Backend & Frontend Engineer / Database Architect / QA Lead / DevSecOps Engineer
> **Date:** 2026-09-19
> **Status:** Requirements Analysis Complete — NO CODE YET

---

## 1. Requirement nào RÕ RÀNG (Confident)

Các requirement dưới đây có đủ thông tin để thiết kế và implement mà không cần thêm thông tin:

### Auth & User Management
- Đăng nhập / Đăng xuất với token
- ADMIN tạo tài khoản, khóa/mở, phân quyền
- Role hierarchy: ADMIN > TEACHER > STUDENT (3 role cứng)
- TEACHER chỉ truy cập dữ liệu lớp mình
- STUDENT chỉ truy cập dữ liệu của chính mình
- Audit log cho các hành động nhạy cảm (append-only)

### Class & Enrollment
- TEACHER tạo lớp, sinh invite_code
- STUDENT vào lớp bằng invite_code
- Soft delete enrollment (trace không bị xóa)

### Problem & Problem Bank
- TEACHER tạo problem với test case (sample / hidden)
- Problem có visibility (PRIVATE / CLASS / PUBLIC*)
- Problem không xóa được khi trong Exam ONGOING

### Exam
- Exam lifecycle: DRAFT → SCHEDULED → ONGOING → ENDED
- Scheduler tự động chuyển trạng thái
- STUDENT chỉ vào Exam khi ONGOING + thuộc lớp
- Exam không sửa được khi ONGOING

### Digital Trace — Core (Đây là phần chắc nhất)
- Phải ghi: PROBLEM_OPENED, FIRST_CODE_INPUT, EDITOR_CHANGE, RUN_EXECUTED, SUBMISSION_MADE, SESSION_ENDED
- EDITOR_CHANGE: timestamp + operation_type + content_diff + changed_range + sequence_number
- KHÔNG lưu full snapshot mỗi keystroke
- Snapshot tạo khi: RUN, SUBMIT, CHECKPOINT
- Snapshot immutable
- Mọi event có client_timestamp + server_timestamp + session_id + sequence_number
- client_timestamp không phải authoritative
- Trace append-only (không UPDATE/DELETE)
- Duplicate prevention: session_id + sequence_number
- Batch ingest API

### Idle & Signal
- Idle = gap giữa meaningful events (EDITOR_CHANGE / RUN / SUBMIT)
- Threshold: >= 5 phút
- Signal = ATTENTION SIGNAL + evidence
- Signal KHÔNG kết luận: gian lận / không hiểu / yếu
- LOC anomaly là signal tương đối, không absolute threshold

### Code Runner
- Sandbox hoàn toàn tách biệt API process
- Giới hạn: CPU, RAM, execution time, filesystem, network
- Trả về: output, result, error_message, execution_time_ms

### Teacher Observation
- Xem danh sách học sinh có signal chưa acknowledged
- Xem timeline trace theo chronological order
- Xem code snapshot tại từng điểm
- Ghi chú annotation (chỉ mình mình sửa)
- TEACHER là người diễn giải, hệ thống không diễn giải thay

---

## 2. Requirement CHƯA RÕ (Unresolved)

Các phần sau chưa đủ thông tin để thiết kế hoặc có ambiguity:

| # | Phần | Vấn đề | OQ |
|---|------|---------|-----|
| 1 | Session luyện tập | Mỗi lần mở bài = Session mới hay resume? | OQ-01 |
| 2 | Login rate limit | N lần sai, cơ chế lockout, ai unlock | OQ-02 |
| 3 | Email notification | Bắt buộc hay optional, provider? | OQ-03 |
| 4 | ADMIN lockout protection | Logic bảo vệ ADMIN duy nhất | OQ-04, OQ-05 |
| 5 | Config threshold | Danh sách đầy đủ threshold ADMIN có thể sửa | OQ-06 |
| 6 | Class name uniqueness | Trùng tên lớp có cho phép không | OQ-07 |
| 7 | Enrollment approval | Tự động hay TEACHER duyệt | OQ-08 |
| 8 | Problem draft validation | Có cần test case để lưu không | OQ-09 |
| 9 | Problem PUBLIC scope | PUBLIC = ai thấy? | OQ-10 |
| 10 | Assignment module | Flow chi tiết (deadline, điểm, submit nhiều lần?) | OQ-12 |
| 11 | Session recovery | Disconnect và reconnect xử lý thế nào | OQ-13 |
| 12 | Live trace view | Real-time hay chỉ after session? | OQ-14 |
| 13 | Student history permission | Ai cấp quyền, điều kiện? | OQ-15 |
| 14 | Gamification | Điểm tích lũy hoạt động thế nào? | OQ-16 |
| 15 | Checkpoint trigger | "Checkpoint phù hợp" — tần suất, điều kiện cụ thể? | — |
| 16 | Ngôn ngữ code runner | Python? C++? Java? | OQ-22 |

---

## 3. Assumption đang được dùng

Các assumption này được chọn để tránh block hoàn toàn analysis.  
**Chúng chưa được xác nhận bởi stakeholder.**

| # | Assumption | Ảnh hưởng nếu sai |
|---|-----------|-------------------|
| A-01 | Session luyện tập: mỗi lần mở bài = Session mới | Phải redesign session model |
| A-02 | Enrollment: tự động approved khi invite_code đúng | Cần thêm approval workflow |
| A-03 | Problem PUBLIC = tất cả STUDENT trong hệ thống thấy, không phải internet | Phải xem lại visibility model |
| A-04 | Problem DRAFT: được lưu không cần test case; không publish được nếu thiếu | Validation logic thay đổi |
| A-05 | Client buffer trace và retry khi mất kết nối | Cần rõ ràng hơn về offline behavior |
| A-06 | Live trace view: không có trong MVP, xem sau session | Architecture khác nếu cần real-time |
| A-07 | STUDENT mặc định xem lịch sử bài luyện tập; xem kết quả thi sau khi Exam ENDED + allow_view_result_after=true | Permission logic phức tạp hơn |
| A-08 | Chỉ có idle_threshold là configurable ở MVP | Cần thêm config nếu có thêm threshold |
| A-09 | Checkpoint: tạo snapshot mỗi N phút trong khi làm bài (N chưa xác định, giả sử 10 phút) | Tần suất snapshot ảnh hưởng storage |
| A-10 | LOC anomaly: so sánh với median LOC của bài đó (relative, không absolute) | Algorithm signal cần rõ hơn |
| A-11 | Email: optional trong MVP | Nếu bắt buộc, cần email infra ngay từ đầu |
| A-12 | Không cho ADMIN tự khóa mình; phải có ít nhất 1 ADMIN active | Business rule thay đổi |

---

## 4. Phần CHƯA được phép code

Theo PROJECT_RULES #3: **"Không được code module tiếp theo nếu module hiện tại chưa PASS kiểm tra."**

Hiện tại **không có module nào** đã pass kiểm tra vì **chưa có module nào được code**.

Tất cả các phần dưới đây **CHƯA được phép thiết kế kỹ thuật chi tiết** vì:
1. Phân tích yêu cầu chưa được stakeholder approve.
2. Nhiều OQ vẫn OPEN.

| Phần | Lý do chưa được code |
|------|---------------------|
| Database schema | OQ chưa resolved; domain model chưa approved |
| API design | Phụ thuộc schema và business rules chưa rõ |
| Code runner implementation | Ngôn ngữ hỗ trợ (OQ-22) chưa xác định |
| Signal Engine logic | LOC anomaly algorithm chưa rõ |
| Assignment module | Flow chi tiết (OQ-12) chưa rõ |
| Live trace view | Infrastructure decision (OQ-14) chưa rõ |
| Gamification | Cơ chế điểm (OQ-16) chưa rõ |
| Email notification | Provider, template (OQ-03) chưa rõ |
| Frontend | Phụ thuộc API chưa có |
| Infrastructure | Sizing (OQ-17, OQ-18, OQ-19) chưa rõ |

---

## 5. Tài liệu đã tạo

| File | Mô tả | Trạng thái |
|------|-------|------------|
| [00_SCOPE.md](./00_SCOPE.md) | Vision, goals, non-goals, actors, boundaries, constraints | DONE |
| [01_DOMAIN.md](./01_DOMAIN.md) | Domain model, entities, invariants, ubiquitous language | DONE |
| [02_USE_CASES.md](./02_USE_CASES.md) | 27 use cases với actor/pre-condition/flow/auth/post-condition | DONE |
| [03_REQUIREMENTS.md](./03_REQUIREMENTS.md) | Requirement Traceability Matrix (REQ-ID, Actor, Priority, Module, AC) | DONE |
| [04_NON_FUNCTIONAL_REQUIREMENTS.md](./04_NON_FUNCTIONAL_REQUIREMENTS.md) | Performance, Security, Scalability, Ethics, Maintainability | DONE |
| [OPEN_QUESTIONS.md](./OPEN_QUESTIONS.md) | 22 open questions chưa được resolved | DONE |

---

## 6. Bước tiếp theo (khi nhận được approval)

Khi stakeholder resolve các OQ và approve tài liệu này:

1. **Resolve OQ** → Update OPEN_QUESTIONS.md
2. **Database schema design** → Từ domain model
3. **API contract design** → OpenAPI spec
4. **Module implementation order** (tuần tự, không song song):
   - Auth → User → Class → Problem → Exam → Trace → Signal → Observation
5. **Infrastructure setup** → Dựa trên sizing từ OQ-17/18/19

**KHÔNG thực hiện bước nào ở trên cho đến khi có approval.**
