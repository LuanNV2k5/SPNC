# 02 — USE CASES

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline
> **Date:** 2026-09-19
> **Status:** DRAFT — Phase 00 Baseline

---

## Quy ước

- **Actor chính:** Actor khởi tạo use case.
- **Pre-condition:** Điều kiện phải đúng trước khi use case bắt đầu.
- **Main Flow:** Luồng chính thành công.
- **Alternative Flow:** Nhánh phụ (error, exception, variation).
- **Authorization:** Rule kiểm tra quyền (enforce tại backend).
- **Post-condition:** Trạng thái hệ thống sau khi use case kết thúc thành công.
- **Priority:** MUST / SHOULD / COULD / OUT-OF-SCOPE.

---

## MODULE A — AUTHENTICATION & USER MANAGEMENT

---

### UC-A01: Đăng nhập

- **ID:** UC-A01
- **Priority:** MUST
- **Actor chính:** User (ADMIN / TEACHER / STUDENT)

**Pre-condition:**
- User tồn tại trong hệ thống.
- AccountStatus = ACTIVE.

**Main Flow:**
1. User nhập username/email và password.
2. Hệ thống xác thực credentials.
3. Hệ thống kiểm tra AccountStatus = ACTIVE.
4. Hệ thống phát hành access token + refresh token.
5. Hệ thống ghi AuditLog: LOGIN_SUCCESS.
6. Nếu `must_change_password = true` → redirect đến UC-A08 (đổi mật khẩu bắt buộc).
7. User được chuyển đến dashboard theo role.

**Alternative Flow:**
- A1: Sai credentials → trả lỗi, không tiết lộ field nào sai. Ghi AuditLog: LOGIN_FAILED.
- A2: AccountStatus = LOCKED → trả lỗi rõ ràng "Tài khoản bị khóa". Ghi AuditLog: LOGIN_FAILED_LOCKED.
- A3: Quá N lần sai liên tiếp → tạm thời rate-limit. **[OQ-02]**

**Authorization:** Không yêu cầu (endpoint public).

**Post-condition:**
- Session token hợp lệ được phát hành.
- AuditLog được ghi.

---

### UC-A02: Đăng xuất

- **ID:** UC-A02
- **Priority:** MUST
- **Actor chính:** User (bất kỳ role)

**Pre-condition:** User đang đăng nhập.

**Main Flow:**
1. User request logout.
2. Hệ thống invalidate refresh token hiện tại.
3. Ghi AuditLog: LOGOUT.

**Alternative Flow:**
- A1: Token đã hết hạn → logout thành công (idempotent). Ghi AuditLog: LOGOUT_ALREADY_EXPIRED.

**Authorization:** Phải là user sở hữu token.

**Post-condition:** Token không còn hợp lệ.

---

### UC-A03: ADMIN tạo tài khoản

- **ID:** UC-A03
- **Priority:** MUST
- **Actor chính:** ADMIN

**Pre-condition:** ADMIN đã đăng nhập, AccountStatus = ACTIVE.

**Main Flow:**
1. ADMIN nhập thông tin: username, email, role, mật khẩu tạm.
2. Hệ thống kiểm tra trùng username/email.
3. Hệ thống tạo tài khoản với status = ACTIVE, must_change_password = true.
4. Hệ thống gửi email thông báo cho user mới. **[OQ-03]**
5. Ghi AuditLog: ACCOUNT_CREATED.

**Alternative Flow:**
- A1: Username/email đã tồn tại → lỗi, không tạo.
- A2: Email không hợp lệ → validation error.

**Authorization:** Chỉ ADMIN.

**Post-condition:** Tài khoản mới tồn tại với role được chỉ định, must_change_password = true.

---

### UC-A04: ADMIN khóa/mở tài khoản

- **ID:** UC-A04
- **Priority:** MUST
- **Actor chính:** ADMIN

**Pre-condition:** ADMIN đã đăng nhập. Tài khoản target tồn tại.

**Main Flow:**
1. ADMIN chọn tài khoản cần thay đổi status.
2. ADMIN chọn hành động: LOCK hoặc UNLOCK.
3. Hệ thống cập nhật AccountStatus.
4. Nếu LOCK: invalidate tất cả active session của user đó.
5. Ghi AuditLog: ACCOUNT_LOCKED / ACCOUNT_UNLOCKED.

**Alternative Flow:**
- A1: ADMIN tự khóa chính mình → từ chối, trả lỗi.
- A2: Khóa ADMIN duy nhất còn lại → từ chối nếu áp dụng business rule "phải có ít nhất 1 ADMIN ACTIVE". **[OQ-04]**

**Authorization:** Chỉ ADMIN.

**Post-condition:** AccountStatus đã thay đổi. Session bị invalidate nếu LOCK.

---

### UC-A05: ADMIN phân quyền (đổi role)

- **ID:** UC-A05
- **Priority:** MUST
- **Actor chính:** ADMIN

**Pre-condition:** ADMIN đã đăng nhập. Tài khoản target tồn tại.

**Main Flow:**
1. ADMIN chọn tài khoản.
2. ADMIN chọn role mới.
3. Nếu role mới = role cũ → ghi AuditLog: ROLE_CHANGE_NOOP, trả thông báo "Role không thay đổi". (fix Mi-01)
4. Nếu role khác: hệ thống cập nhật role.
5. Invalidate session hiện tại của user đó.
6. Ghi AuditLog: ROLE_CHANGED.

**Alternative Flow:**
- A1: ADMIN tự đổi role của chính mình → **[OQ-05]**

**Authorization:** Chỉ ADMIN.

**Post-condition:** User có role mới khi đăng nhập lại. AuditLog luôn được ghi.

---

### UC-A06: ADMIN xem audit log

- **ID:** UC-A06
- **Priority:** MUST
- **Actor chính:** ADMIN

**Pre-condition:** ADMIN đã đăng nhập.

**Main Flow:**
1. ADMIN truy cập audit log.
2. ADMIN lọc theo: thời gian, actor, action type, target.
3. Hệ thống trả về danh sách log có pagination.

**Alternative Flow:** Không có.

**Authorization:** Chỉ ADMIN.

**Post-condition:** Log được hiển thị. Không có thay đổi dữ liệu.

---

### UC-A07: ADMIN cấu hình threshold hệ thống

- **ID:** UC-A07
- **Priority:** SHOULD
- **Actor chính:** ADMIN

**Pre-condition:** ADMIN đã đăng nhập.

**Main Flow:**
1. ADMIN xem danh sách threshold có thể cấu hình.
2. ADMIN chỉnh sửa giá trị (ví dụ: idle_threshold_minutes).
3. Hệ thống validate giá trị hợp lệ (> 0, trong giới hạn cho phép).
4. Hệ thống lưu cấu hình.
5. Ghi AuditLog: CONFIG_CHANGED (ghi giá trị cũ và mới).

**Threshold có thể cấu hình:**
- `idle_threshold_minutes` (default: 5, min: 1, max: 60)
- Danh sách đầy đủ → **[OQ-06]**

**Alternative Flow:**
- A1: Giá trị không hợp lệ (âm, vượt giới hạn) → validation error với message rõ ràng.

**Authorization:** Chỉ ADMIN.

**Post-condition:** Cấu hình mới được áp dụng cho các session mới.

---

### UC-A08: User đổi mật khẩu của chính mình (NEW — fix M-05, B10)

- **ID:** UC-A08
- **Priority:** MUST
- **Actor chính:** User (ADMIN / TEACHER / STUDENT)

**Pre-condition:** User đã đăng nhập (hoặc đang trong luồng first-login với must_change_password = true).

**Main Flow:**
1. User nhập mật khẩu hiện tại (hoặc mật khẩu tạm nếu first login).
2. User nhập mật khẩu mới và xác nhận.
3. Hệ thống xác thực mật khẩu hiện tại.
4. Hệ thống kiểm tra mật khẩu mới đủ độ mạnh.
5. Hệ thống cập nhật password_hash.
6. Hệ thống set must_change_password = false.
7. Hệ thống invalidate tất cả refresh token cũ (trừ session hiện tại).
8. Ghi AuditLog: PASSWORD_CHANGED.

**Alternative Flow:**
- A1: Mật khẩu hiện tại sai → lỗi.
- A2: Mật khẩu mới không đủ mạnh → validation error với hướng dẫn cụ thể.
- A3: Mật khẩu mới = mật khẩu hiện tại → cảnh báo hoặc từ chối. **[OQ-02 liên quan]**

**Authorization:** User chỉ đổi mật khẩu của chính mình.

**Post-condition:** Password mới có hiệu lực. must_change_password = false. Session cũ trên thiết bị khác bị invalidate.

---

### UC-A09: ADMIN xem danh sách user và tài nguyên hệ thống (NEW — fix M-03, M-04, B11)

- **ID:** UC-A09
- **Priority:** MUST
- **Actor chính:** ADMIN

**Pre-condition:** ADMIN đã đăng nhập.

**Main Flow:**
1. ADMIN xem danh sách tất cả user (filter theo role, status, pagination).
2. ADMIN xem danh sách tất cả lớp học trong hệ thống (read-only).
3. ADMIN xem danh sách tất cả kỳ thi (read-only, filter theo status).
4. ADMIN xem basic system settings.

**Alternative Flow:** Không có.

**Authorization:** Chỉ ADMIN. ADMIN không được chỉnh sửa nội dung học thuật (problem, exam content) của TEACHER trong V1. **[OQ-23 liên quan với emergency action]**

**Post-condition:** Không thay đổi dữ liệu. Thông tin hệ thống được hiển thị.

---

## MODULE B — CLASS MANAGEMENT

---

### UC-B01: TEACHER tạo lớp

- **ID:** UC-B01
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER đã đăng nhập, AccountStatus = ACTIVE.

**Main Flow:**
1. TEACHER nhập thông tin lớp: tên, mô tả.
2. Hệ thống tạo lớp với teacher_id = TEACHER hiện tại, status = ACTIVE.
3. Hệ thống sinh invite_code duy nhất.

**Alternative Flow:**
- A1: Tên lớp trùng với lớp khác của cùng TEACHER → **[OQ-07]**

**Authorization:** Chỉ TEACHER (và ADMIN đọc system-wide).

**Post-condition:** Lớp mới được tạo, TEACHER là owner.

---

### UC-B02: TEACHER quản lý thông tin lớp

- **ID:** UC-B02
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner của lớp. AccountStatus = ACTIVE.

**Main Flow:**
1. TEACHER chọn lớp.
2. TEACHER sửa tên, mô tả, hoặc thay đổi status.
3. Hệ thống validate thay đổi.
4. Hệ thống lưu thay đổi.

**Alternative Flow:**
- A1: Lớp đang có Exam ONGOING → không cho archive/close. Trả lỗi rõ ràng.
- A2: TEACHER không phải owner → 403.

**Authorization:** Chỉ TEACHER owner. ADMIN read-only system-wide.

**Post-condition:** Thông tin lớp được cập nhật.

---

### UC-B03: STUDENT tham gia lớp

- **ID:** UC-B03
- **Priority:** MUST
- **Actor chính:** STUDENT

**Pre-condition:**
- STUDENT đã đăng nhập.
- AccountStatus = ACTIVE. (fix Mi-04 — kiểm tra tại backend)
- Lớp có status = ACTIVE.

**Main Flow:**
1. STUDENT nhập invite_code.
2. Hệ thống tìm lớp theo invite_code.
3. Hệ thống kiểm tra STUDENT chưa enrolled (enrollment ACTIVE chưa tồn tại).
4. Hệ thống tạo Enrollment với status = ACTIVE.

**Alternative Flow:**
- A1: invite_code không hợp lệ hoặc không tìm thấy lớp → lỗi.
- A2: STUDENT đã enrolled ACTIVE → thông báo "Bạn đã tham gia lớp này".
- A3: Lớp CLOSED hoặc ARCHIVED → không cho tham gia.
- A4: AccountStatus = LOCKED → 403 mặc dù token còn hợp lệ. (fix Mi-04, B14)
- A5: **[OQ-08: TEACHER có cần duyệt enrollment không?]**

**Authorization:** Chỉ STUDENT (AccountStatus = ACTIVE).

**Post-condition:** Enrollment được tạo.

---

### UC-B04: TEACHER quản lý học sinh trong lớp

- **ID:** UC-B04
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner lớp.

**Main Flow:**
1. TEACHER xem danh sách học sinh (enrollment ACTIVE).
2. TEACHER có thể remove học sinh khỏi lớp.

**Alternative Flow:**
- A1: Remove học sinh → Enrollment status = REMOVED (soft delete). Trace vẫn giữ nguyên. AuditLog: STUDENT_REMOVED.

**Authorization:** Chỉ TEACHER owner. ADMIN có thể override.

**Post-condition:** Enrollment status = REMOVED.

---

## MODULE C — PROBLEM MANAGEMENT

---

### UC-C01: TEACHER tạo câu hỏi lập trình

- **ID:** UC-C01
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER đã đăng nhập.

**Main Flow:**
1. TEACHER nhập: tiêu đề, mô tả, ràng buộc, định dạng input/output, độ khó, ngôn ngữ cho phép.
2. TEACHER thêm test cases (input, expected output, is_sample, score_weight).
3. TEACHER đặt visibility (PRIVATE / CLASS / PUBLIC).
4. Hệ thống lưu Problem với author_id = TEACHER.

**Alternative Flow:**
- A1: Không có test case → warning nhưng vẫn cho lưu ở trạng thái draft. **[OQ-09]**
- A2: Visibility = PUBLIC → Problem hiển thị với mọi STUDENT và TEACHER trong hệ thống. **[OQ-24: cross-teacher reuse?]**
- A3: Visibility = CLASS → yêu cầu chọn Class để tạo ClassProblemPublication.

**Authorization:** Chỉ TEACHER.

**Post-condition:** Problem được lưu với author_id = TEACHER.

---

### UC-C02: TEACHER chỉnh sửa câu hỏi

- **ID:** UC-C02
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là author. Problem không đang trong Exam SCHEDULED / ONGOING.

**Main Flow:**
1. TEACHER chỉnh sửa nội dung bài.
2. Hệ thống lưu thay đổi.

**Alternative Flow:**
- A1: Problem đang trong Exam SCHEDULED hoặc ONGOING → từ chối. Trả lỗi rõ ràng.
- A2: TEACHER không phải author → 403.

**Authorization:** TEACHER là author, hoặc ADMIN (read-only V1).

**Post-condition:** Problem được cập nhật.

---

### UC-C03: TEACHER quản lý kho đề

- **ID:** UC-C03
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER đã đăng nhập.

**Main Flow:**
1. TEACHER xem danh sách problem của mình (lọc theo độ khó, ngôn ngữ, visibility).
2. TEACHER thêm/xóa problem khỏi ProblemBank của mình.
3. TEACHER phát hành problem có visibility = CLASS tới một lớp cụ thể (tạo ClassProblemPublication).

**Alternative Flow:**
- A1: Xóa problem đang trong Exam ACTIVE/ONGOING → từ chối.

**Authorization:** Chỉ TEACHER owner.

**Post-condition:** Kho đề được cập nhật.

---

## MODULE D — EXAM MANAGEMENT

---

### UC-D01: TEACHER tạo kỳ thi

- **ID:** UC-D01
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner của lớp. Lớp status = ACTIVE.

**Main Flow:**
1. TEACHER nhập: tiêu đề, start_time, end_time, duration_minutes, lớp.
2. TEACHER chọn problems từ kho đề, sắp xếp thứ tự, gán điểm.
3. TEACHER cấu hình: allow_view_result_after.
4. Hệ thống tạo Exam với status = DRAFT.

**Alternative Flow:**
- A1: start_time < now → lỗi.
- A2: end_time <= start_time → lỗi.
- A3: Không có problem → vẫn cho lưu DRAFT. Không cho publish. **[OQ-11]**

**Authorization:** Chỉ TEACHER owner của lớp.

**Post-condition:** Exam được tạo với status = DRAFT.

---

### UC-D02: TEACHER publish kỳ thi

- **ID:** UC-D02
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** Exam status = DRAFT. Có ít nhất 1 problem. start_time > now.

**Main Flow:**
1. TEACHER review Exam.
2. TEACHER publish.
3. Hệ thống đổi status = SCHEDULED.
4. Scheduler (server-side) tự động đổi status = ONGOING khi đến start_time.
5. Scheduler (server-side) tự động đổi status = ENDED khi đến end_time.

**Alternative Flow:**
- A1: Điều kiện pre-condition không thỏa → lỗi rõ ràng với từng điều kiện.

**Authorization:** Chỉ TEACHER owner.

**Post-condition:** Exam = SCHEDULED.

---

### UC-D03: STUDENT tham gia kỳ thi

- **ID:** UC-D03
- **Priority:** MUST
- **Actor chính:** STUDENT

**Pre-condition:**
- STUDENT enrolled vào lớp (Enrollment.status = ACTIVE).
- Exam status = ONGOING.
- Thời gian hiện tại trong [start_time, end_time].
- ExamParticipation chưa có hoặc status = NOT_STARTED.

**Main Flow:**
1. STUDENT mở Exam.
2. Hệ thống tạo hoặc cập nhật ExamParticipation: status = IN_PROGRESS, started_at = now.
3. STUDENT thấy danh sách bài và thời gian còn lại (server-side countdown).
4. STUDENT bắt đầu làm từng bài (xem UC-E02).
5. Khi Exam ENDED (server-side): active ExamParticipation → status = EXPIRED, expired_at = now.

**Alternative Flow:**
- A1: Exam ENDED và allow_view_result_after = true → STUDENT xem kết quả.
- A2: Exam ENDED và allow_view_result_after = false → từ chối xem.
- A3: STUDENT không enrolled → 403.
- A4: ExamParticipation.status = COMPLETED → thông báo "Bạn đã hoàn thành kỳ thi".
- A5: Exam CANCELLED → thông báo "Kỳ thi đã bị hủy".

**Authorization:** Chỉ STUDENT enrolled vào lớp có Exam này.

**Post-condition:** ExamParticipation tồn tại với status = IN_PROGRESS.

---

### UC-D04: TEACHER gán bài cho lớp (ngoài kỳ thi)

- **ID:** UC-D04
- **Priority:** SHOULD
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner lớp.

**Main Flow:**
1. TEACHER chọn problem(s).
2. TEACHER gán cho lớp (tạo ClassProblemPublication hoặc Assignment entity).
3. Học sinh trong lớp thấy bài trong danh sách luyện tập.

**Alternative Flow:** Flow chi tiết chưa rõ. **[OQ-12]**

**Authorization:** Chỉ TEACHER owner.

**Post-condition:** Problem được phát hành tới lớp.

---

### UC-D05: TEACHER cancel kỳ thi (NEW — fix Mi-05, B13)

- **ID:** UC-D05
- **Priority:** SHOULD
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner của Exam. Exam status = DRAFT hoặc SCHEDULED.

**Main Flow:**
1. TEACHER chọn Exam cần cancel.
2. TEACHER nhập lý do cancel.
3. Hệ thống đổi Exam.status = CANCELLED.
4. Hệ thống cập nhật: cancelled_at = now, cancelled_by = TEACHER.id, cancel_reason.
5. Nếu có ExamParticipation đang IN_PROGRESS → chuyển sang CANCELLED.
6. Ghi AuditLog: EXAM_CANCELLED.

**Alternative Flow:**
- A1: Exam status = ONGOING → từ chối. Trả lỗi. **[OQ-23: admin emergency cancel]**
- A2: Exam status = ENDED → không thể cancel.
- A3: TEACHER không phải owner → 403.

**Authorization:** Chỉ TEACHER owner. ADMIN cancel khi ONGOING → OQ-23.

**Post-condition:** Exam.status = CANCELLED. Active participation → CANCELLED. AuditLog ghi nhận. Không kết luận gì về học sinh.

---

## MODULE E — CODING & TRACE

---

### UC-E01: STUDENT xem kho bài luyện tập

- **ID:** UC-E01
- **Priority:** SHOULD
- **Actor chính:** STUDENT

**Pre-condition:** STUDENT đã đăng nhập, AccountStatus = ACTIVE.

**Main Flow:**
1. STUDENT xem danh sách problem được phép truy cập (visibility = PUBLIC, hoặc CLASS với ClassProblemPublication trong lớp mình).
2. STUDENT lọc theo độ khó, ngôn ngữ, trạng thái (chưa làm, đã làm, đã ACCEPTED).
3. STUDENT chọn bài để làm (→ UC-E02).

**Alternative Flow:**
- A1: Không có bài nào → thông báo.

**Authorization:** STUDENT chỉ thấy problem có quyền truy cập theo visibility.

**Post-condition:** Không có thay đổi dữ liệu.

---

### UC-E02: STUDENT làm bài (viết code, run, submit)

- **ID:** UC-E02
- **Priority:** MUST
- **Actor chính:** STUDENT

**Pre-condition:**
- STUDENT đã đăng nhập, AccountStatus = ACTIVE.
- Problem tồn tại và STUDENT có quyền truy cập.
- Nếu là Exam: ExamParticipation.status = IN_PROGRESS.

**Main Flow:**

**Bước 1 — Mở bài:**
1. STUDENT mở problem.
2. Hệ thống kiểm tra quyền truy cập.
3. Hệ thống tạo Session (status = ACTIVE).
4. Hệ thống ghi TraceEvent `PROBLEM_OPENED` với `problem_open_time` = server_timestamp.

**Bước 2 — Code:**
5. STUDENT đọc đề, bắt đầu gõ code.
6. Khi gõ ký tự đầu tiên: ghi TraceEvent `FIRST_CODE_INPUT` với `first_code_event_time`.
7. Mỗi thay đổi code: ghi TraceEvent `EDITOR_CHANGE` với:
   - `operation_type`: INSERT | DELETE | REPLACE
   - `range_offset`, `range_length`, `text`
   - `editor_version`
   - `input_source` (optional)
   - `sequence_number` monotonic tăng
8. Client buffer events và gửi batch về server.
9. Server assign `server_timestamp` và lưu (idempotent theo session_id + sequence_number).

**Bước 3 — Run:**
10. STUDENT nhấn "Run":
    a. Hệ thống tạo CodeSnapshot (trigger_reason = RUN).
    b. Hệ thống ghi TraceEvent `SESSION_CHECKPOINT` với code_snapshot_id.
    c. Hệ thống gửi code đến Code Runner (sandbox, tách biệt API process).
    d. Code Runner thực thi với giới hạn CPU/RAM/time/filesystem/network.
    e. Hệ thống ghi TraceEvent `RUN_EXECUTED` với: input_used, output, result, error_message, code_snapshot_id, execution_time_ms.

**Bước 4 — Submit:**
11. STUDENT nhấn "Submit":
    a. Hệ thống tạo CodeSnapshot (trigger_reason = SUBMIT).
    b. Hệ thống tạo Submission.
    c. Code Runner chấm với hidden test cases.
    d. Hệ thống ghi TraceEvent `SUBMISSION_MADE` với code_snapshot_id, submission_id.
    e. Hệ thống ghi TraceEvent `SESSION_ENDED` với final_code_snapshot_id, final_loc, working_time_seconds, termination_actor = STUDENT.
    f. Session.status → ENDED, Session.termination_actor = STUDENT.
12. STUDENT xem kết quả (verdict, per-testcase nếu cho phép).

**Alternative Flow:**
- A1: Code Runner timeout → kết quả TLE, vẫn ghi trace.
- A2: Code compile error → kết quả COMPILE_ERROR, vẫn ghi trace.
- A3: Exam hết giờ trong lúc làm bài:
  - Server-side: Exam.status → ENDED.
  - Server finalize: nếu có code snapshot gần nhất server đã nhận → tạo Submission với source = SYSTEM_EXAM_TIMEOUT.
  - Nếu không có snapshot nào → Submission không được tạo (không fabricate code).
  - Session.status → ENDED, termination_actor = SYSTEM_EXAM_TIMEOUT.
  - ExamParticipation.status → EXPIRED.
- A4: STUDENT disconnect: client buffer events, retry khi có kết nối. Server idempotent insert. **[OQ-13]**
- A5: Idle >= idle_threshold → System Engine tạo AttentionSignal IDLE_DETECTED (tự động, không hỏi STUDENT, không kết luận gì).
- A6: STUDENT mở bài nhưng không submit (thoát): Session.status → ABANDONED theo session policy. **[OQ-01]**

**Authorization:**
- Đọc problem: STUDENT có quyền truy cập theo visibility.
- Submit trong Exam: STUDENT enrolled + ExamParticipation IN_PROGRESS.
- Code Runner: không access network, filesystem ngoài sandbox.

**Post-condition:**
- TraceEvent được ghi (append-only).
- CodeSnapshot được tạo tại Run/Submit/Checkpoint.
- Submission được tạo (nếu submit xảy ra).
- Session.status rõ ràng (ENDED hoặc ABANDONED).
- AttentionSignal có thể được sinh nếu có hiện tượng observable.

---

### UC-E03: Signal Engine sinh Attention Signal

- **ID:** UC-E03
- **Priority:** MUST
- **Actor chính:** System (tự động)

**Pre-condition:** Session đang ACTIVE hoặc vừa ENDED.

**Main Flow:**
1. System tính khoảng cách giữa các meaningful event (EDITOR_CHANGE, RUN_EXECUTED, SUBMISSION_MADE).
2. Nếu gap >= idle_threshold → tạo AttentionSignal(IDLE_DETECTED) với evidence factual:
   - Wording: "Không ghi nhận meaningful activity trong N phút." (KHÔNG phán xét)
3. System tính LOC cuối session.
4. Nếu LOC bất thường so với context (tương đối) → tạo AttentionSignal(LOC_ANOMALY) với evidence.
5. Signal được lưu với status = NEW, không kết luận gì thêm.

**Alternative Flow:**
- A1: Không có gì bất thường → không tạo signal.

**Authorization:** Internal system. Không expose API public.

**Post-condition:** AttentionSignal được lưu với evidence JSON factual, status = NEW, không có nhận định chủ quan.

---

## MODULE F — TEACHER OBSERVATION

---

### UC-F01: TEACHER xem học sinh cần chú ý

- **ID:** UC-F01
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER đã đăng nhập. Có ít nhất một lớp.

**Main Flow:**
1. TEACHER chọn lớp.
2. Hệ thống hiển thị danh sách "NEEDS ATTENTION": học sinh có AttentionSignal status = NEW.
3. TEACHER xem summary signal (signal_type, detected_at, evidence summary) theo học sinh.
4. TEACHER có thể navigate sang Session list của học sinh đó (→ UC-F05).

**Alternative Flow:**
- A1: Không có signal mới → thông báo "Không có học sinh cần chú ý".

**Authorization:** Chỉ TEACHER owner lớp. Chỉ học sinh thuộc lớp đó.

**Post-condition:** Không thay đổi dữ liệu.

---

### UC-F02: TEACHER xem timeline dấu vết chi tiết

- **ID:** UC-F02
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner lớp chứa học sinh. Session thuộc học sinh thuộc lớp đó.

**Main Flow:**
1. TEACHER chọn Session cụ thể (từ UC-F05: Session List).
2. Hệ thống trả về timeline event theo thứ tự chronological (server_timestamp).
3. TEACHER thấy:
   - Thời điểm mở đề (PROBLEM_OPENED)
   - Thời điểm gõ đầu tiên (FIRST_CODE_INPUT)
   - Các EDITOR_CHANGE events
   - Các idle gaps (khoảng trống giữa meaningful events)
   - Các lần Run (RUN_EXECUTED) với input/output/result/error/execution_time_ms
   - Các checkpoint snapshots (SESSION_CHECKPOINT)
   - Submit (SUBMISSION_MADE)
   - Kết thúc session (SESSION_ENDED với termination_actor)
4. TEACHER có thể click vào bất kỳ điểm có snapshot để xem code tại thời điểm đó.

**Alternative Flow:**
- A1: Session.status = ACTIVE (đang diễn ra) → xem trace đã ghi đến thời điểm hiện tại (không stream raw code realtime, sử dụng REST + WebSocket updates trong V1) (OQ-14 RESOLVED)

**Authorization:** Chỉ TEACHER owner lớp.

**Post-condition:** Không thay đổi dữ liệu.

---

### UC-F03: TEACHER ghi chú đánh giá (mở rộng — fix M-08, B12)

- **ID:** UC-F03
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER đã đăng nhập và có quyền quan sát học sinh trong lớp.

**Sub-flows:**

**F03-A: Tạo annotation:**
1. TEACHER nhập nội dung ghi chú.
2. TEACHER chọn context: student_id (bắt buộc), session_id (optional), signal_id (optional).
3. Hệ thống lưu TeacherAnnotation với teacher_id, created_at.

**F03-B: Xem/lọc annotation của mình:**
1. TEACHER xem danh sách annotation đã tạo.
2. TEACHER lọc theo: student, session, signal, thời gian.

**F03-C: Sửa annotation:**
1. TEACHER chọn annotation của mình.
2. TEACHER sửa content.
3. Hệ thống lưu với updated_at.

**F03-D: Xóa annotation:**
1. TEACHER chọn annotation của mình.
2. TEACHER xác nhận xóa.
3. Hệ thống xóa annotation.

**Alternative Flow:**
- A1 (bất kỳ sub-flow): Học sinh không thuộc lớp TEACHER → 403.
- A2 (F03-C/D): Annotation không phải của TEACHER này → 403.

**Authorization:** TEACHER chỉ create/update/delete annotation của chính mình. TEACHER chỉ annotate học sinh trong lớp mình.

**Post-condition:**
- F03-A: Annotation được tạo.
- F03-B: Không thay đổi dữ liệu.
- F03-C: Annotation được cập nhật.
- F03-D: Annotation bị xóa (hard delete hoặc soft delete tùy implementation). **[OQ-06 liên quan]**

---

### UC-F04: TEACHER xem kết quả và thống kê

- **ID:** UC-F04
- **Priority:** SHOULD
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner lớp.

**Main Flow:**
1. TEACHER chọn lớp / kỳ thi.
2. Hệ thống hiển thị: điểm trung bình, phân bổ điểm, tỷ lệ ACCEPTED/non-ACCEPTED, thời gian làm trung bình.
3. TEACHER xem per-student: điểm, số lần run, submission count, session count.

**Alternative Flow:**
- A1: Chưa có submission → thống kê rỗng.

**Authorization:** Chỉ TEACHER owner.

**Post-condition:** Không thay đổi dữ liệu.

---

### UC-F05: TEACHER xem danh sách Sessions của học sinh (NEW — fix C-02, B2)

- **ID:** UC-F05
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner lớp. Học sinh thuộc lớp đó.

**Main Flow:**
1. TEACHER chọn lớp → chọn học sinh cụ thể.
2. Hệ thống trả về danh sách Sessions của học sinh đó, filter theo lớp này.
3. Mỗi Session trong danh sách hiển thị:
   - `problem.title`
   - context: exam title hoặc "Practice"
   - `started_at`
   - `ended_at` (null nếu ACTIVE)
   - `status` (ACTIVE / ENDED / ABANDONED)
   - `termination_actor`
   - Latest meaningful event timestamp
   - Submission status (nếu có: verdict)
   - AttentionSignal count (số signal của session đó)
4. TEACHER click vào Session để xem timeline chi tiết (→ UC-F02).

**Alternative Flow:**
- A1: Học sinh chưa có session nào → danh sách rỗng.
- A2: Học sinh không thuộc lớp TEACHER → 403.

**Authorization:** Chỉ TEACHER owner lớp. Chỉ thấy session của học sinh trong lớp mình.

**Post-condition:** Không thay đổi dữ liệu.

---

### UC-F06: TEACHER quan sát kỳ thi (Exam Observation — NEW — fix C-04, B3)

- **ID:** UC-F06
- **Priority:** MUST
- **Actor chính:** TEACHER

**Pre-condition:** TEACHER là owner Exam. Exam status = ONGOING hoặc ENDED.

**Main Flow:**
1. TEACHER chọn Exam.
2. Hệ thống hiển thị danh sách học sinh trong lớp với trạng thái:
   - NOT_STARTED: Chưa mở Exam
   - IN_PROGRESS: Đang làm
   - COMPLETED: Đã finalize
   - EXPIRED: Hết giờ mà chưa finalize
   - CANCELLED: Exam bị cancel
3. Với mỗi học sinh, TEACHER thấy:
   - ExamParticipation.status
   - Số bài đã submit (derive từ Submission count)
   - Session hiện tại (nếu IN_PROGRESS): started_at, latest activity, run count
   - AttentionSignal count (nếu có)
4. TEACHER click vào học sinh cụ thể để xem Session detail (→ UC-F05 → UC-F02).

> Đây là **OBSERVATION**, không phải automatic evaluation. TEACHER quan sát thực tế, không có hệ thống kết luận thay TEACHER.

**Alternative Flow:**
- A1: Exam ENDED → hiển thị kết quả cuối cùng của tất cả học sinh.
- A2: Không có học sinh nào bắt đầu → danh sách toàn NOT_STARTED.

**Authorization:** Chỉ TEACHER owner Exam.

**Post-condition:** Không thay đổi dữ liệu.

---

## MODULE G — STUDENT HISTORY & GAMIFICATION

---

### UC-G01: STUDENT xem lịch sử bài của mình

- **ID:** UC-G01
- **Priority:** SHOULD
- **Actor chính:** STUDENT

> **OUT-OF-SCOPE CLARIFICATION (fix C-01, NG10):**
> STUDENT KHÔNG được xem raw digital trace, editor timeline, attention signal, hoặc code replay của chính mình trong V1. Digital Trace Observation là chức năng dành riêng cho TEACHER.

**Pre-condition:** STUDENT đã đăng nhập. Được phép xem kết quả. **[OQ-15]**

**Main Flow:**
1. STUDENT xem danh sách bài đã làm (problems với submission history).
2. STUDENT chọn bài → xem submission history của mình (chỉ các submission của mình).
3. STUDENT xem: verdict, score, judge_result (per-testcase nếu cho phép), submitted_at.
4. STUDENT xem code snapshot của submission của mình (nội dung code tại thời điểm submit).

> STUDENT không xem: TraceEvent, idle gap, AttentionSignal, TeacherAnnotation.

**Alternative Flow:**
- A1: Chưa có submission → danh sách rỗng.
- A2: Không được phép xem (Exam chưa ENDED hoặc allow_view_result_after = false) → ẩn.

**Authorization:**
- STUDENT chỉ xem dữ liệu của chính mình.
- STUDENT không xem submission/trace của học sinh khác.

**Post-condition:** Không thay đổi dữ liệu.

---

### UC-G02: STUDENT tích điểm

- **ID:** UC-G02
- **Priority:** SHOULD
- **Actor chính:** STUDENT, System

**Pre-condition:** Submission có verdict ACCEPTED.

**Main Flow:**
1. System tính điểm cho Submission.
2. System cộng điểm vào profile STUDENT.

**Alternative Flow:** **[OQ-16: Cơ chế tích điểm cụ thể như thế nào?]**

**Authorization:** Internal system.

**Post-condition:** Điểm STUDENT được cập nhật.

---

## USE CASE INDEX (Cập nhật đầy đủ)

| UC ID | Tên | Module | Priority | Actor | Fix |
|-------|-----|--------|----------|-------|-----|
| UC-A01 | Đăng nhập | Auth | MUST | All | Updated |
| UC-A02 | Đăng xuất | Auth | MUST | All | — |
| UC-A03 | ADMIN tạo tài khoản | User Mgmt | MUST | ADMIN | Updated |
| UC-A04 | ADMIN khóa/mở tài khoản | User Mgmt | MUST | ADMIN | — |
| UC-A05 | ADMIN phân quyền | User Mgmt | MUST | ADMIN | Mi-01 fix |
| UC-A06 | ADMIN xem audit log | Audit | MUST | ADMIN | — |
| UC-A07 | ADMIN cấu hình threshold | Config | SHOULD | ADMIN | — |
| UC-A08 | User đổi mật khẩu | Auth | MUST | All | **NEW** M-05 |
| UC-A09 | ADMIN xem system-wide | Admin | MUST | ADMIN | **NEW** M-03/M-04 |
| UC-B01 | TEACHER tạo lớp | Class | MUST | TEACHER | — |
| UC-B02 | TEACHER quản lý lớp | Class | MUST | TEACHER | — |
| UC-B03 | STUDENT tham gia lớp | Class | MUST | STUDENT | Mi-04 fix |
| UC-B04 | TEACHER quản lý học sinh | Class | MUST | TEACHER | — |
| UC-C01 | TEACHER tạo problem | Problem | MUST | TEACHER | Updated |
| UC-C02 | TEACHER sửa problem | Problem | MUST | TEACHER | — |
| UC-C03 | TEACHER quản lý kho đề | Problem | MUST | TEACHER | Updated |
| UC-D01 | TEACHER tạo kỳ thi | Exam | MUST | TEACHER | — |
| UC-D02 | TEACHER publish kỳ thi | Exam | MUST | TEACHER | — |
| UC-D03 | STUDENT tham gia kỳ thi | Exam | MUST | STUDENT | M-06 fix |
| UC-D04 | TEACHER gán bài cho lớp | Assignment | SHOULD | TEACHER | — |
| UC-D05 | TEACHER cancel kỳ thi | Exam | SHOULD | TEACHER | **NEW** Mi-05 |
| UC-E01 | STUDENT xem kho bài | Practice | SHOULD | STUDENT | — |
| UC-E02 | STUDENT làm bài | Coding/Trace | MUST | STUDENT | C-03/C-05 fix |
| UC-E03 | System sinh attention signal | Signal | MUST | System | — |
| UC-F01 | TEACHER xem NEEDS ATTENTION | Observation | MUST | TEACHER | — |
| UC-F02 | TEACHER xem timeline | Observation | MUST | TEACHER | — |
| UC-F03 | TEACHER ghi chú đánh giá (CRUD) | Observation | MUST | TEACHER | **EXPANDED** M-08 |
| UC-F04 | TEACHER xem thống kê | Analytics | SHOULD | TEACHER | — |
| UC-F05 | TEACHER xem danh sách Sessions | Observation | MUST | TEACHER | **NEW** C-02 |
| UC-F06 | TEACHER quan sát kỳ thi | Observation | MUST | TEACHER | **NEW** C-04 |
| UC-G01 | STUDENT xem lịch sử (submission only) | History | SHOULD | STUDENT | C-01 clarified |
| UC-G02 | STUDENT tích điểm | Gamification | SHOULD | STUDENT/System | — |
