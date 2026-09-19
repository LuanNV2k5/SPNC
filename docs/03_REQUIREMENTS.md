# 03 — FUNCTIONAL REQUIREMENTS

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline
> **Date:** 2026-09-19
> **Status:** DRAFT

---

## Quy ước cột

| Cột | Ý nghĩa |
|-----|---------|
| **REQ-ID** | Định danh duy nhất |
| **Requirement** | Phát biểu requirement |
| **Actor** | Ai chịu trách nhiệm / bị ảnh hưởng |
| **Priority** | MUST / SHOULD / COULD |
| **Module** | Module chức năng |
| **Use Case** | UC liên quan |
| **Acceptance Criteria** | Điều kiện kiểm chứng cụ thể — không được dùng "phù hợp", "hợp lý", "TBD" |
| **Status** | ACTIVE / DEFERRED / OUT-OF-SCOPE |

---

## Requirement Traceability Matrix

### AUTH — Authentication & Authorization

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-AUTH-001** | Hệ thống phải xác thực người dùng bằng username/email và password | All | MUST | Auth | UC-A01 | Login đúng credentials → token được phát hành; sai credentials → 401 với message chung, không tiết lộ field nào sai | ACTIVE |
| **REQ-AUTH-002** | Hệ thống phải phát hành access token và refresh token sau khi đăng nhập thành công | All | MUST | Auth | UC-A01 | Token hợp lệ, có expiry; dùng được trong các request tiếp theo | ACTIVE |
| **REQ-AUTH-003** | Hệ thống phải ghi AuditLog cho mọi lần đăng nhập (thành công và thất bại) | System | MUST | Auth / Audit | UC-A01 | AuditLog có entry với action=LOGIN_SUCCESS hoặc LOGIN_FAILED sau mỗi login attempt | ACTIVE |
| **REQ-AUTH-004** | Hệ thống phải invalidate refresh token khi người dùng đăng xuất | All | MUST | Auth | UC-A02 | Refresh token cũ không dùng được sau logout; trả 401 nếu thử dùng | ACTIVE |
| **REQ-AUTH-005** | Hệ thống phải từ chối request không có token hợp lệ ở các endpoint bảo vệ | All | MUST | Auth | All | Request không có token → 401; token sai/hết hạn → 401 | ACTIVE |
| **REQ-AUTH-006** | Authorization phải được kiểm tra tại backend, không chỉ ẩn button frontend | All | MUST | Auth | All | Gọi trực tiếp API với role không đủ quyền → 403 kể cả khi frontend không hiển thị button | ACTIVE |
| **REQ-AUTH-007** | Hệ thống phải kiểm tra AccountStatus tại backend với mọi protected operation (fix B14, Mi-04) | All | MUST | Auth | All | User bị LOCK → 403 kể cả khi access token chưa hết hạn | ACTIVE |

### USER — User Management

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-USER-001** | ADMIN phải tạo được tài khoản với role chỉ định | ADMIN | MUST | User Mgmt | UC-A03 | Tài khoản mới tồn tại với role đúng, status=ACTIVE, must_change_password=true | ACTIVE |
| **REQ-USER-002** | ADMIN phải khóa/mở tài khoản bất kỳ | ADMIN | MUST | User Mgmt | UC-A04 | AccountStatus thay đổi; session bị invalidate khi LOCK; AuditLog ghi ACCOUNT_LOCKED/UNLOCKED | ACTIVE |
| **REQ-USER-003** | Tài khoản LOCKED không thể thực hiện protected operation | System | MUST | User Mgmt | UC-A04 | Login với LOCKED → 401; API call với token của LOCKED user → 403 | ACTIVE |
| **REQ-USER-004** | ADMIN phải thay đổi được role của user | ADMIN | MUST | User Mgmt | UC-A05 | Role mới có hiệu lực sau khi user đăng nhập lại; AuditLog ghi ROLE_CHANGED hoặc ROLE_CHANGE_NOOP | ACTIVE |
| **REQ-USER-005** | ADMIN phải xem được danh sách user với filter (role, status) và pagination | ADMIN | MUST | User Mgmt | UC-A09 | Danh sách trả về đúng theo filter; có pagination với page/limit params | ACTIVE |
| **REQ-USER-006** | ADMIN phải xem và lọc audit log | ADMIN | MUST | Audit | UC-A06 | Audit log hiển thị với filter theo thời gian, actor_id, action, target_type; có pagination | ACTIVE |
| **REQ-USER-007** | ADMIN phải cấu hình được idle_threshold (configurable, không phải hardcode) | ADMIN | SHOULD | Config | UC-A07 | Giá trị mới (min=1, max=60 phút) được áp dụng cho các session mới; cũ không bị thay đổi; AuditLog ghi CONFIG_CHANGED với giá trị cũ và mới | ACTIVE |
| **REQ-USER-008** | User phải đổi được mật khẩu của chính mình (fix M-05, B10) | All | MUST | Auth | UC-A08 | Đổi thành công với mật khẩu hiện tại đúng; must_change_password → false; session cũ bị invalidate | ACTIVE |
| **REQ-USER-009** | User tạo với mật khẩu tạm phải bắt buộc đổi mật khẩu khi đăng nhập lần đầu (fix B10) | System | MUST | Auth | UC-A01, UC-A08 | User có must_change_password=true → redirect đổi mật khẩu; không được thực hiện operation khác cho đến khi đổi xong | ACTIVE |
| **REQ-USER-010** | ADMIN phải xem danh sách tất cả lớp và kỳ thi trong hệ thống (read-only) (fix M-04) | ADMIN | MUST | Admin | UC-A09 | ADMIN xem được list tất cả Class và Exam với filter/pagination; không thể sửa nội dung học thuật | ACTIVE |

### CLASS — Class Management

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-CLASS-001** | TEACHER phải tạo được lớp với invite_code duy nhất | TEACHER | MUST | Class | UC-B01 | Lớp tạo thành công với teacher_id đúng; invite_code không trùng với lớp khác trong hệ thống | ACTIVE |
| **REQ-CLASS-002** | TEACHER phải chỉnh sửa được thông tin lớp mình | TEACHER | MUST | Class | UC-B02 | Thay đổi được lưu; TEACHER không phải owner → 403 | ACTIVE |
| **REQ-CLASS-003** | TEACHER phải xem danh sách học sinh trong lớp | TEACHER | MUST | Class | UC-B04 | Danh sách chỉ chứa học sinh thuộc lớp mình; học sinh lớp khác không xuất hiện | ACTIVE |
| **REQ-CLASS-004** | TEACHER phải xóa được học sinh khỏi lớp (soft delete) | TEACHER | MUST | Class | UC-B04 | Enrollment.status = REMOVED; trace của học sinh vẫn còn; học sinh không còn thấy bài lớp đó | ACTIVE |
| **REQ-CLASS-005** | STUDENT phải tham gia lớp bằng invite_code | STUDENT | MUST | Class | UC-B03 | Enrollment được tạo khi code đúng và lớp ACTIVE và STUDENT ACTIVE | ACTIVE |
| **REQ-CLASS-006** | TEACHER không được truy cập lớp của TEACHER khác | System | MUST | Class | UC-B02 | API trả 403 khi TEACHER không phải owner cố update/delete lớp | ACTIVE |

### PROBLEM — Problem Management

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-PROB-001** | TEACHER phải tạo được problem với đầy đủ fields bắt buộc | TEACHER | MUST | Problem | UC-C01 | Problem được lưu với title, description, constraints, input_format, output_format, author_id đúng | ACTIVE |
| **REQ-PROB-002** | TEACHER phải thêm test case (input, expected_output, is_sample, score_weight) | TEACHER | MUST | Problem | UC-C01 | Test case được lưu; is_sample=true → hiển thị cho STUDENT; is_sample=false → ẩn | ACTIVE |
| **REQ-PROB-003** | TEACHER phải đặt được visibility cho problem và hệ thống enforce đúng | TEACHER | MUST | Problem | UC-C01 | PRIVATE: chỉ author + ADMIN; CLASS: chỉ STUDENT enrolled lớp có publication; PUBLIC: mọi STUDENT enrolled bất kỳ lớp | ACTIVE |
| **REQ-PROB-004** | TEACHER không được sửa problem đang trong Exam SCHEDULED hoặc ONGOING | System | MUST | Problem | UC-C02 | API trả lỗi khi cố sửa; cho phép sửa khi Exam DRAFT/ENDED/CANCELLED | ACTIVE |
| **REQ-PROB-005** | Problem không thể xóa khi đang dùng trong Exam ACTIVE hoặc ONGOING | System | MUST | Problem | UC-C02 | API trả lỗi khi cố xóa; cho phép xóa khi không còn Exam active | ACTIVE |
| **REQ-PROB-006** | TEACHER phải xem và quản lý kho đề của mình với filter | TEACHER | MUST | Problem Bank | UC-C03 | Danh sách problem đúng của TEACHER đó; filter theo difficulty/language/visibility hoạt động | ACTIVE |
| **REQ-PROB-007** | Problem visibility = CLASS phải được enforce qua ClassProblemPublication (fix M-01) | System | MUST | Problem | UC-C01, UC-C03 | STUDENT không trong lớp có publication → 403 khi truy cập CLASS problem; STUDENT trong lớp → 200 | ACTIVE |

### EXAM — Exam Management

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-EXAM-001** | TEACHER phải tạo được kỳ thi với start_time, end_time, duration_minutes, lớp | TEACHER | MUST | Exam | UC-D01 | Exam được tạo với status=DRAFT; start_time < end_time; start_time > now khi publish | ACTIVE |
| **REQ-EXAM-002** | Exam phải tự động chuyển sang ONGOING khi đến start_time (server-side) | System | MUST | Exam | UC-D02 | Status = ONGOING trong vòng 60 seconds sau start_time (theo scheduler tolerance); không phụ thuộc client request | ACTIVE |
| **REQ-EXAM-003** | Exam phải tự động chuyển sang ENDED khi đến end_time (server-side) | System | MUST | Exam | UC-D02 | Status = ENDED trong vòng 60 seconds sau end_time (theo scheduler tolerance); không phụ thuộc client request | ACTIVE |
| **REQ-EXAM-004** | TEACHER phải gán problem vào Exam theo thứ tự và điểm tối đa | TEACHER | MUST | Exam | UC-D01 | ExamProblem được tạo đúng với order và max_score; thứ tự thay đổi được khi DRAFT | ACTIVE |
| **REQ-EXAM-005** | STUDENT chỉ truy cập Exam của lớp mình khi đang ONGOING | System | MUST | Exam | UC-D03 | STUDENT không enrolled → 403; Exam SCHEDULED/DRAFT/ENDED → 403 (trừ ENDED+allow_view) | ACTIVE |
| **REQ-EXAM-006** | Exam không thể chỉnh sửa khi ONGOING | System | MUST | Exam | UC-D01 | API trả lỗi khi cố sửa Exam ONGOING; chỉ cho sửa khi DRAFT | ACTIVE |
| **REQ-EXAM-007** | TEACHER phải cấu hình allow_view_result_after | TEACHER | MUST | Exam | UC-D01 | STUDENT xem kết quả chỉ khi flag=true VÀ Exam ENDED; flag=false → 403 | ACTIVE |
| **REQ-EXAM-008** | TEACHER gán được bài tập cho lớp ngoài kỳ thi | TEACHER | SHOULD | Assignment | UC-D04 | STUDENT trong lớp thấy bài trong danh sách luyện tập sau khi được gán | ACTIVE |
| **REQ-EXAM-009** | ExamParticipation phải có status rõ ràng (NOT_STARTED/IN_PROGRESS/COMPLETED/EXPIRED/CANCELLED) (fix M-06, CON-04) | System | MUST | Exam | UC-D03 | Status chính xác theo hành động; EXPIRED khi Exam ENDED mà chưa COMPLETED; không dùng submitted_at đơn lẻ | ACTIVE |
| **REQ-EXAM-010** | TEACHER phải cancel được Exam ở trạng thái DRAFT hoặc SCHEDULED (fix Mi-05, B13) | TEACHER | SHOULD | Exam | UC-D05 | Exam.status = CANCELLED; cancelled_at, cancelled_by, cancel_reason được lưu; AuditLog: EXAM_CANCELLED | ACTIVE |
| **REQ-EXAM-011** | Khi Exam CANCELLED: active ExamParticipation → CANCELLED; không tạo/giả lập submission | System | SHOULD | Exam | UC-D05 | ExamParticipation.status = CANCELLED; không có Submission mới được tạo do cancel | ACTIVE |
| **REQ-EXAM-012** | Authorization truy cập Exam phải kiểm tra cả ExamStatus lẫn authoritative time-window (fix Mi-NEW-03) | System | MUST | Exam | UC-D03 | STUDENT bị từ chối nếu current_time ∉ [start_time, end_time] KHÔNG PHỤ THUỘC vào materialized ExamStatus; scheduler lag không được trở thành authorization bypass | ACTIVE |

### TRACE — Digital Trace Collection

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-TRACE-001** | Khi STUDENT mở bài, phải ghi event PROBLEM_OPENED với server_timestamp | System | MUST | Trace | UC-E02 | Event PROBLEM_OPENED tồn tại trong DB; server_timestamp được gán bởi server | ACTIVE |
| **REQ-TRACE-002** | Khi STUDENT gõ code lần đầu, phải ghi event FIRST_CODE_INPUT | System | MUST | Trace | UC-E02 | Event FIRST_CODE_INPUT tồn tại; chỉ được tạo một lần per session | ACTIVE |
| **REQ-TRACE-003** | Mỗi thay đổi code phải tạo event EDITOR_CHANGE với đầy đủ fields (fix C-03, B4) | System | MUST | Trace | UC-E02 | Event có: operation_type ∈ {INSERT, DELETE, REPLACE}; range_offset ≥ 0; range_length ≥ 0; text (string); editor_version; sequence_number monotonic; invalid operation_type → rejected | ACTIVE |
| **REQ-TRACE-004** | EDITOR_CHANGE phải lưu diff (range_offset + range_length + text), KHÔNG lưu full code content | System | MUST | Trace | UC-E02 | DB không chứa full code content tại mỗi EDITOR_CHANGE; chỉ CodeSnapshot chứa full content | ACTIVE |
| **REQ-TRACE-005** | Mỗi sự kiện trace phải có client_timestamp VÀ server_timestamp | System | MUST | Trace | UC-E02 | Cả 2 field tồn tại trong mọi event; server_timestamp được server gán | ACTIVE |
| **REQ-TRACE-006** | server_timestamp là authoritative; client_timestamp không được dùng cho deadline enforcement | System | MUST | Trace | UC-E02 | Logic tính idle, working_time, exam deadline dùng server_timestamp; client_timestamp chỉ lưu làm tham chiếu | ACTIVE |
| **REQ-TRACE-007** | Mọi sự kiện trace phải có session_id và sequence_number hợp lệ | System | MUST | Trace | UC-E02 | Mọi event có session_id tồn tại trong DB; sequence_number là **1-based positive integer** (first event=1); sequence_number=0 hoặc negative → rejected (fix Mi-NEW-04) | ACTIVE |
| **REQ-TRACE-008** | Trace event phải append-only | System | MUST | Trace | UC-E02 | Không có UPDATE hoặc DELETE endpoint cho trace events; DB constraint enforce | ACTIVE |
| **REQ-TRACE-009** | Hệ thống phải chống duplicate trace bằng (session_id, sequence_number) | System | MUST | Trace | UC-E02 | Insert cùng session_id + sequence_number lần 2 → idempotent, không tạo duplicate; trả 200/202 bình thường | ACTIVE |
| **REQ-TRACE-010** | API ingest trace phải hỗ trợ batch | System | MUST | Trace | UC-E02 | API nhận array events trong một request; tối thiểu 100 events per batch | ACTIVE |
| **REQ-TRACE-011** | Khi STUDENT Run, phải tạo CodeSnapshot (RUN) và ghi RUN_EXECUTED đầy đủ (fix Mi-02, B16) | System | MUST | Trace | UC-E02 | CodeSnapshot tồn tại với trigger_reason=RUN; event RUN_EXECUTED có: code_snapshot_id, input_used, output, result, error_message, execution_time_ms (integer ms ≥ 0) | ACTIVE |
| **REQ-TRACE-012** | Khi STUDENT Submit, phải tạo CodeSnapshot (SUBMIT) và ghi SUBMISSION_MADE | System | MUST | Trace | UC-E02 | CodeSnapshot tồn tại với trigger_reason=SUBMIT; Submission được tạo; event SUBMISSION_MADE có code_snapshot_id và submission_id | ACTIVE |
| **REQ-TRACE-013** | Hệ thống phải tạo snapshot tại các checkpoint định kỳ VÀ ghi SESSION_CHECKPOINT event tương ứng (fix Mi-03, B15) | System | SHOULD | Trace | UC-E02 | CodeSnapshot tồn tại với trigger_reason=CHECKPOINT; SESSION_CHECKPOINT event tồn tại với code_snapshot_id trỏ đến đúng snapshot đó | ACTIVE |
| **REQ-TRACE-014** | CodeSnapshot phải immutable sau khi tạo | System | MUST | Trace | UC-E02 | Không có UPDATE endpoint/query cho code_snapshots; content không thay đổi sau khi lưu | ACTIVE |
| **REQ-TRACE-015** | Khi Session kết thúc, phải ghi SESSION_ENDED với final_loc, working_time, termination_actor | System | MUST | Trace | UC-E02 | Event SESSION_ENDED tồn tại; final_loc = số dòng code cuối; working_time_seconds ≥ 0; termination_actor ∈ {STUDENT, SYSTEM_EXAM_TIMEOUT, SYSTEM_SESSION_POLICY} | ACTIVE |

### SESSION — Session Lifecycle (NEW — fix C-05, CON-03, B5)

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-SESSION-001** | Session phải có status rõ ràng: ACTIVE / ENDED / ABANDONED | System | MUST | Session | UC-E02 | Session.status tồn tại và có giá trị hợp lệ; ACTIVE khi đang làm; ENDED khi kết thúc thành công hoặc Exam timeout; ABANDONED theo configurable stale policy | ACTIVE |
| **REQ-SESSION-002** | Session phải ghi rõ termination_actor khi kết thúc | System | MUST | Session | UC-E02 | Session.termination_actor ∈ {STUDENT, SYSTEM_EXAM_TIMEOUT, SYSTEM_SESSION_POLICY}; không null khi status = ENDED hoặc ABANDONED | ACTIVE |
| **REQ-SESSION-003** | Exam timeout PHẢI được enforce server-side — không phụ thuộc client gửi SESSION_ENDED | System | MUST | Session | UC-E02 | Khi Exam ENDED (server scheduler): tất cả active Session trong Exam → ENDED với termination_actor = SYSTEM_EXAM_TIMEOUT | ACTIVE |
| **REQ-SESSION-004** | Khi Exam timeout: nếu có snapshot server đã nhận → finalize submission; nếu không → không fabricate code | System | MUST | Session | UC-E02 | Submission được tạo từ snapshot gần nhất nếu tồn tại; không tạo Submission từ code không được server nhận | ACTIVE |
| **REQ-SESSION-005** | IDLE signal và ABANDONED session là hai khái niệm riêng biệt — IDLE không tự chuyển session sang ABANDONED (fix Mi-NEW-01) | System | MUST | Session | UC-E02, UC-E03 | idle interval >= idle_threshold → chỉ tạo AttentionSignal IDLE_DETECTED; Session.status KHÔNG thay đổi; Practice Session chỉ ABANDONED theo configurable stale policy riêng biệt | ACTIVE |

### IDLE — Idle Detection & Signal

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-IDLE-001** | Hệ thống phải tính idle interval từ khoảng cách giữa meaningful events | System | MUST | Signal | UC-E03 | Idle interval = server_timestamp gap giữa 2 meaningful events liên tiếp (EDITOR_CHANGE, RUN_EXECUTED, SUBMISSION_MADE) | ACTIVE |
| **REQ-IDLE-002** | Khi idle interval >= idle_threshold, phải tạo AttentionSignal IDLE_DETECTED | System | MUST | Signal | UC-E03 | AttentionSignal được tạo với evidence: {start_time, end_time, duration_seconds, meaningful_event_before_id, threshold_used}; status = NEW | ACTIVE |
| **REQ-IDLE-003** | AttentionSignal evidence KHÔNG được chứa kết luận nhận định tiêu cực về học sinh | System | MUST | Signal | UC-E03 | Mọi field của AttentionSignal không chứa từ: "gian lận", "không hiểu", "yếu", "có vấn đề", "đáng ngờ"; wording phải factual (ví dụ: "Không ghi nhận meaningful activity trong N phút") | ACTIVE |

### SIGNAL — Attention Signal

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-SIGNAL-001** | Hệ thống phải tính final LOC khi session kết thúc | System | MUST | Signal | UC-E02 | Session.final_loc = số dòng code trong final snapshot; SESSION_ENDED event có final_loc | ACTIVE |
| **REQ-SIGNAL-002** | LOC anomaly signal phải dùng threshold tương đối, không absolute | System | SHOULD | Signal | UC-E03 | Signal LOC_ANOMALY evidence chứa: final_loc, context_median_loc (của bài đó), delta; không có hardcoded absolute threshold | ACTIVE |
| **REQ-SIGNAL-003** | AttentionSignal phải có evidence JSON không rỗng và có thể kiểm chứng | System | MUST | Signal | UC-E03 | evidence JSON không null, không rỗng; chứa ít nhất: signal_type-specific fields theo §1.8 domain | ACTIVE |
| **REQ-SIGNAL-004** | Hệ thống KHÔNG được kết luận gian lận, không hiểu bài, hoặc yếu | System | MUST | Signal | UC-E03 | Kiểm tra toàn bộ signal_type labels, evidence content, API response: không có từ phán xét | ACTIVE |
| **REQ-SIGNAL-005** | AttentionSignal phải có rule_version để traceability | System | SHOULD | Signal | UC-E03 | rule_version không null; khi algorithm signal thay đổi, rule_version tăng | ACTIVE |

### OBS — Teacher Observation

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-OBS-001** | TEACHER phải xem được danh sách học sinh "NEEDS ATTENTION" trong lớp | TEACHER | MUST | Observation | UC-F01 | Danh sách chỉ chứa học sinh có AttentionSignal.status=NEW; chỉ học sinh của lớp TEACHER | ACTIVE |
| **REQ-OBS-002** | TEACHER phải xem được danh sách Sessions của học sinh (fix C-02, B2) | TEACHER | MUST | Observation | UC-F05 | Danh sách Sessions hiển thị: problem, context, started_at, ended_at, status, termination_actor, latest_activity, submission_verdict, signal_count; chỉ học sinh thuộc lớp TEACHER | ACTIVE |
| **REQ-OBS-003** | TEACHER phải xem được timeline dấu vết chi tiết của một Session | TEACHER | MUST | Observation | UC-F02 | Timeline hiển thị đầy đủ events theo server_timestamp: PROBLEM_OPENED, FIRST_CODE_INPUT, EDITOR_CHANGE, RUN_EXECUTED, SESSION_CHECKPOINT, SUBMISSION_MADE, SESSION_ENDED | ACTIVE |
| **REQ-OBS-004** | TEACHER phải xem được code snapshot tại từng điểm trong timeline | TEACHER | MUST | Observation | UC-F02 | Xem snapshot tại bất kỳ event có code_snapshot_id; content đúng với thời điểm đó | ACTIVE |
| **REQ-OBS-005** | TEACHER phải ghi chú được (create/read/update/delete) annotation (fix M-08, B12) | TEACHER | MUST | Observation | UC-F03 | Create: annotation lưu với teacher_id, student_id, created_at; Update: chỉ owner mới sửa; Delete: chỉ owner mới xóa; Read: list với filter theo student/session/signal | ACTIVE |
| **REQ-OBS-006** | TEACHER chỉ annotate/observe học sinh trong lớp mình | System | MUST | Observation | UC-F03 | API trả 403 nếu học sinh không thuộc lớp TEACHER đang request | ACTIVE |
| **REQ-OBS-007** | TEACHER phải xem được thống kê kết quả lớp/kỳ thi | TEACHER | SHOULD | Analytics | UC-F04 | Hiển thị: điểm trung bình, phân bổ điểm, tỷ lệ ACCEPTED/non-ACCEPTED, thời gian làm trung bình; tính từ Submission data | ACTIVE |
| **REQ-OBS-008** | TEACHER phải xem tổng quan Exam Observation (fix C-04, B3) | TEACHER | MUST | Observation | UC-F06 | Hiển thị mỗi STUDENT: ExamParticipation.status, số bài đã submit, AttentionSignal count; chỉ học sinh lớp TEACHER | ACTIVE |

### RUN — Code Runner

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-RUN-001** | Code học sinh phải chạy trong sandbox hoàn toàn tách biệt API process | System | MUST | Code Runner | UC-E02 | API process không trực tiếp execute code student; code runner là process/container riêng biệt | ACTIVE |
| **REQ-RUN-002** | Code runner phải giới hạn CPU, RAM, execution time, filesystem, network | System | MUST | Code Runner | UC-E02 | Run bị kill khi vượt bất kỳ giới hạn nào; sandbox không access external network; không write ra ngoài tmpdir | ACTIVE |
| **REQ-RUN-003** | Code runner phải trả về đầy đủ: output, result, error_message, execution_time_ms | System | MUST | Code Runner | UC-E02 | Mọi field tồn tại trong response; execution_time_ms là integer ≥ 0 | ACTIVE |
| **REQ-RUN-004** | Code runner chấm submission theo hidden test cases và trả verdict + per-testcase result | System | MUST | Code Runner | UC-E02 | Verdict ∈ {ACCEPTED, WRONG_ANSWER, TLE, RUNTIME_ERROR, COMPILE_ERROR, PENDING}; JudgeResult có per-testcase detail | ACTIVE |
| **REQ-RUN-005** | Code Runner phải hỗ trợ chính thức CPP17 và PYTHON3 trong V1 (OQ-22) | System | MUST | Code Runner | UC-E02 | language_allowed chỉ chấp nhận CPP17 hoặc PYTHON3; ngôn ngữ khác → 422 với error code UNSUPPORTED_LANGUAGE; Judge extensible để thêm language sau | ACTIVE |

### STUDENT — Student Features

| REQ-ID | Requirement | Actor | Priority | Module | Use Case | Acceptance Criteria | Status |
|--------|-------------|-------|----------|--------|----------|---------------------|--------|
| **REQ-STU-001** | STUDENT phải xem được danh sách bài luyện tập mình có quyền truy cập | STUDENT | SHOULD | Practice | UC-E01 | Danh sách đúng theo visibility; PUBLIC problem và CLASS problem từ lớp đang enrolled | ACTIVE |
| **REQ-STU-002** | STUDENT phải xem được lịch sử submission của mình nếu được phép | STUDENT | SHOULD | History | UC-G01 | STUDENT xem verdict/score/code của submission mình; không xem submission học sinh khác | ACTIVE |
| **REQ-STU-003** | STUDENT KHÔNG được xem raw trace / attention signal trong V1 | System | MUST | Privacy | UC-G01 | API trả 403 khi STUDENT cố truy cập TraceEvent hoặc AttentionSignal không phải của mình; Raw trace viewer là OUT-OF-SCOPE V1 | ACTIVE |
| **REQ-STU-004** | STUDENT phải tích điểm khi có submission ACCEPTED | STUDENT | SHOULD | Gamification | UC-G02 | Điểm được cộng sau verdict = ACCEPTED; cơ chế tích lũy theo OQ-16 | ACTIVE |
| **REQ-STU-005** | STUDENT không thể bắt đầu Practice CodingSession khi đang có ExamParticipation = IN_PROGRESS (fix Mi-NEW-05) | System | MUST | Practice | UC-E01, UC-E02 | API trả domain error ACTIVE_EXAM_IN_PROGRESS; STUDENT phải finalize hoặc chờ Exam kết thúc trước khi luyện tập | ACTIVE |

---

## Requirements Count Summary

| Module | MUST | SHOULD | COULD | Total |
|--------|------|--------|-------|-------|
| AUTH | 7 | 0 | 0 | 7 |
| USER | 8 | 2 | 0 | 10 |
| CLASS | 6 | 0 | 0 | 6 |
| PROBLEM | 7 | 0 | 0 | 7 |
| EXAM | 10 | 2 | 0 | 12 |
| TRACE | 14 | 1 | 0 | 15 |
| SESSION | 5 | 0 | 0 | 5 |
| IDLE | 3 | 0 | 0 | 3 |
| SIGNAL | 3 | 2 | 0 | 5 |
| OBS | 7 | 1 | 0 | 8 |
| RUN | 5 | 0 | 0 | 5 |
| STUDENT | 3 | 2 | 0 | 5 |
| **TOTAL** | **78** | **10** | **0** | **88** |

---

## Changelog

| Version | Date | Thay đổi |
|---------|------|----------|
| 0.1 | 2026-09-19 | Khởi tạo |
| 0.2 | 2026-09-19 | Remediation: +REQ-AUTH-007, +REQ-USER-008/009/010, +REQ-PROB-007, +REQ-EXAM-009/010/011, +REQ-SESSION-001–004, +REQ-SIGNAL-005, +REQ-OBS-002/005/008; Fix REQ-TRACE-003/011/013/015 |
| 0.3 | 2026-09-19 | Final baseline: +REQ-SESSION-005 (ABANDONED≠idle), +REQ-EXAM-012 (dual-check auth), +REQ-RUN-005 (CPP17/PYTHON3), +REQ-STU-005 (practice+exam block); Fix REQ-TRACE-007 (1-based seq_num); Total: 88 REQs |
