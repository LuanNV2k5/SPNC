# 01 — DOMAIN MODEL

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline (OQ-22, Mi-NEW-01/02/04/05)
> **Date:** 2026-09-19
> **Status:** DRAFT

---

## 1. Core Domain Concepts

### 1.1 User & Identity

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **User** | id, username, email, password_hash, role, status, created_at, last_login_at, must_change_password | Base entity |
| **Role** | ADMIN \| TEACHER \| STUDENT | Enum, không phân cấp con |
| **AccountStatus** | ACTIVE \| LOCKED \| PENDING | Chỉ ADMIN thay đổi |

**Quy tắc domain:**
- Một user có đúng một role tại một thời điểm.
- Role thay đổi chỉ qua ADMIN.
- STUDENT bị LOCKED không thể làm bài, nhưng dữ liệu trace vẫn được giữ nguyên.
- `must_change_password = true` khi ADMIN tạo tài khoản với mật khẩu tạm. User phải đổi khi đăng nhập lần đầu.
- Authorization phải kiểm tra AccountStatus tại backend với mọi protected operation — token chưa hết hạn không đủ nếu account bị LOCKED.

---

### 1.2 Class & Enrollment

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **Class** | id, name, description, teacher_id, status, invite_code, created_at | Thuộc về một TEACHER |
| **Enrollment** | id, class_id, student_id, enrolled_at, status | Trạng thái: ACTIVE \| REMOVED |
| **ClassStatus** | ACTIVE \| ARCHIVED \| CLOSED | |

**Quy tắc domain:**
- Một lớp thuộc đúng một TEACHER (owner).
- TEACHER không thể xem lớp của TEACHER khác.
- Học sinh có thể thuộc nhiều lớp.
- Xóa học sinh khỏi lớp là soft delete (REMOVED), không xóa trace.

---

### 1.3 Problem (Câu hỏi lập trình)

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **Problem** | id, title, description, constraints, input_format, output_format, difficulty, language_allowed, author_id, visibility, created_at | |
| **TestCase** | id, problem_id, input, expected_output, is_sample, score_weight | |
| **ProblemVisibility** | PRIVATE \| CLASS \| PUBLIC | Xem định nghĩa chi tiết bên dưới |
| **Difficulty** | EASY \| MEDIUM \| HARD | Label thủ công, không tự động |
| **LanguageIdentifier** | CPP17 \| PYTHON3 | **V1 closed enum** (OQ-22). CPP17 = GCC-compatible C++17. PYTHON3 = Python 3.x runtime. |
| **ClassProblemPublication** | id, problem_id, class_id, published_by (teacher_id), published_at | Bản ghi phát hành problem tới lớp cụ thể |

**Định nghĩa Visibility (fix M-01, B9):**

| Giá trị | Ai thấy problem | Ai xem/sửa |
|---------|----------------|------------|
| **PRIVATE** | Chỉ author TEACHER và ADMIN | Author TEACHER + ADMIN |
| **CLASS** | STUDENT thuộc Class có ClassProblemPublication với problem này + TEACHER owner Class đó | Author TEACHER + ADMIN; Teacher khác: chỉ đọc nếu có publication trong lớp mình |
| **PUBLIC** | Mọi STUDENT đang enrolled trong bất kỳ lớp nào + mọi TEACHER trong hệ thống | Author TEACHER + ADMIN |

**Lưu ý PUBLIC (fix M-02, OQ-24):** PUBLIC không mặc định có nghĩa TEACHER khác được sửa hoặc copy problem. Cross-teacher problem reuse/copy là OPEN QUESTION (OQ-24).

**Quy tắc domain:**
- TestCase có thể có is_sample=true (hiển thị cho STUDENT) hoặc false (hidden, chỉ Code Runner dùng).
- Problem không thể xóa nếu đang dùng trong Exam ACTIVE hoặc ONGOING.
- Để gán problem có visibility = CLASS tới một lớp, phải tạo ClassProblemPublication.

---

### 1.4 Problem Bank (Kho đề)

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **ProblemBank** | id, name, teacher_id, description | Tập hợp problem do TEACHER quản lý |
| **ProblemBankItem** | bank_id, problem_id, added_at | Quan hệ N-M |

**Quy tắc domain:**
- Mỗi TEACHER có kho đề riêng.
- Problem từ kho có thể được đưa vào nhiều Exam.
- TEACHER chỉ quản lý kho đề của chính mình.

---

### 1.5 Exam (Kỳ thi)

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **Exam** | id, title, class_id, teacher_id, start_time, end_time, duration_minutes, status, allow_view_result_after, cancelled_at, cancelled_by, cancel_reason | |
| **ExamProblem** | exam_id, problem_id, order, max_score | Bài trong kỳ thi |
| **ExamStatus** | DRAFT \| SCHEDULED \| ONGOING \| ENDED \| CANCELLED | |
| **ExamParticipation** | id, exam_id, student_id, status, started_at, completed_at, expired_at | Thay thế submitted_at đơn lẻ bằng status model đầy đủ (fix M-06, CON-04, B6) |
| **ExamParticipationStatus** | NOT_STARTED \| IN_PROGRESS \| COMPLETED \| EXPIRED \| CANCELLED | |

**Per-problem completion tracking (fix M-06, B6):**

Trạng thái hoàn thành theo từng bài được xác định bởi sự tồn tại của Submission cho cặp (exam_id, student_id, problem_id). Không tạo entity trung gian riêng trong V1 — derive từ Submission.

| Khái niệm | Định nghĩa |
|-----------|-----------|
| Submit một problem | Tạo Submission với exam_id = Exam này |
| Finalization toàn exam | STUDENT không còn hoạt động / thời gian hết → ExamParticipation = COMPLETED hoặc EXPIRED |
| Timeout | Exam ENDED (server-side) → active ExamParticipation chuyển sang EXPIRED |
| Partial completion | STUDENT submit một số bài, không phải tất cả → ExamParticipation = COMPLETED (vẫn hoàn thành nếu STUDENT tự finalize) |

**Quy tắc domain:**
- STUDENT chỉ thấy Exam của lớp mình đang enrolled.
- STUDENT chỉ truy cập Exam khi status = ONGOING và trong thời gian cho phép.
- Sau khi Exam ENDED, STUDENT xem kết quả chỉ khi `allow_view_result_after = true`.
- Exam không thể chỉnh sửa khi status = ONGOING.
- **CANCELLED flow (fix Mi-05, B13):** TEACHER owner có thể cancel Exam ở trạng thái DRAFT hoặc SCHEDULED. TEACHER không thể cancel Exam đang ONGOING — đây là OPEN QUESTION (OQ-23). Cancel phải ghi AuditLog. Active ExamParticipation → CANCELLED khi Exam bị cancel.

---

### 1.6 Submission (Bài nộp)

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **Submission** | id, student_id, problem_id, exam_id (nullable), session_id, code_snapshot_id, language, submitted_at, verdict, score, judge_result | exam_id null = luyện tập |
| **Verdict** | ACCEPTED \| WRONG_ANSWER \| TIME_LIMIT_EXCEEDED \| RUNTIME_ERROR \| COMPILE_ERROR \| PENDING | |
| **JudgeResult** | Cấu trúc JSON: per-testcase result (testcase_id, passed, execution_time_ms, memory_used_kb) | |

**Quy tắc domain:**
- Một Submission luôn gắn với một Session.
- Mỗi Submission tham chiếu đến một CodeSnapshot (immutable).
- Nếu code_snapshot_id null (do client chưa kịp gửi snapshot trước khi timeout), Submission vẫn được tạo với trạng thái rõ ràng — không fabricate code. (fix C-05, B5)
- Verdict không tự động sinh attention signal. Chỉ dùng làm dữ liệu cho TEACHER phân tích.
- Submission trong Exam chỉ được tạo khi ExamParticipation.status = IN_PROGRESS.

---

### 1.7 Digital Trace — Core Concept

Dấu vết số là **tập hợp các sự kiện có thứ tự thời gian** được ghi lại trong một **Session**.

#### 1.7.1 Session

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **Session** | id, student_id, problem_id, exam_id (nullable), context (EXAM \| PRACTICE), status, started_at, ended_at, termination_actor, working_time_seconds, final_loc | (fix C-05, CON-03, B5) |
| **SessionStatus** | ACTIVE \| ENDED \| ABANDONED | |
| **SessionContext** | EXAM \| PRACTICE | Phân biệt session trong kỳ thi và luyện tập |
| **TerminationActor** | STUDENT \| SYSTEM_EXAM_TIMEOUT \| SYSTEM_SESSION_POLICY | Ghi rõ ai/gì kết thúc session |

**Quy tắc domain:**
- Một Session = một học sinh + một bài + một lần ngồi làm.
- Session bắt đầu (ACTIVE) khi STUDENT mở problem hợp lệ.
- Nếu học sinh thoát và quay lại cùng bài trong cùng kỳ thi → cùng Session (không tạo mới).
- Nếu luyện tập tự do, mỗi lần mở bài = Session mới. **[OQ-01 vẫn OPEN]**
- **Session kết thúc bởi:**
  1. STUDENT submit/finalize → status = ENDED, termination_actor = STUDENT
  2. SYSTEM khi Exam hết giờ → status = ENDED, termination_actor = SYSTEM_EXAM_TIMEOUT
  3. SYSTEM theo configurable stale session policy → status = ABANDONED, termination_actor = SYSTEM_SESSION_POLICY
- **Exam timeout PHẢI được enforce SERVER-SIDE.** Không phụ thuộc browser gửi SESSION_ENDED.
- **ABANDONED semantics (fix Mi-NEW-01):**
  - ABANDONED KHÔNG được dùng cho Exam timeout. Exam timeout → ENDED + SYSTEM_EXAM_TIMEOUT.
  - ABANDONED chỉ dùng cho Practice Session không còn active theo configurable Session Policy.
  - **Idle >= idle_threshold KHÔNG tự động chuyển session sang ABANDONED.** Idle chỉ tạo AttentionSignal.
  - V1 KHÔNG tự đóng Practice Session chỉ vì idle 5 phút.
  - Stale duration để ABANDONED là configurable Session Policy riêng biệt với idle_threshold.
  - Invariant: **IDLE_DETECTED signal ≠ ABANDONED session.**
- **Practice + Exam concurrency (fix Mi-NEW-05):**
  - Khi STUDENT có ExamParticipation = IN_PROGRESS, V1 KHÔNG cho phép bắt đầu Practice CodingSession mới.
  - API reject bằng domain error: `ACTIVE_EXAM_IN_PROGRESS`.
  - Exam Session và Practice Session luôn có SessionContext riêng biệt và KHÔNG bị merge.
- Session ABANDONED không được diễn giải là thất bại của học sinh.

#### 1.7.2 Trace Events (append-only)

**Loại sự kiện:**

| Event Type | Mô tả | Dữ liệu key |
|-----------|--------|-------------|
| `PROBLEM_OPENED` | Học sinh mở đề | `problem_open_time` |
| `FIRST_CODE_INPUT` | Lần đầu nhập code | `first_code_event_time` |
| `EDITOR_CHANGE` | Thay đổi code trong editor | `operation_type`, `range_offset`, `range_length`, `text`, `editor_version`, `input_source` (optional) |
| `RUN_EXECUTED` | Chạy code | `input_used`, `output`, `result`, `error_message`, `code_snapshot_id`, `execution_time_ms` |
| `SUBMISSION_MADE` | Nộp bài | `code_snapshot_id`, `submission_id` |
| `SESSION_CHECKPOINT` | Checkpoint định kỳ — timeline marker | `code_snapshot_id`, `trigger_reason = CHECKPOINT` |
| `SESSION_ENDED` | Kết thúc session | `final_code_snapshot_id`, `final_loc`, `working_time_seconds`, `termination_actor` |

> **Ghi chú B15 (SESSION_CHECKPOINT):** SESSION_CHECKPOINT tồn tại như một event để TEACHER thấy điểm checkpoint trong timeline. Snapshot nội dung được lưu trong CodeSnapshot (trigger_reason = CHECKPOINT). Hai entity phục vụ mục đích khác nhau: event = timeline marker, snapshot = content store. Cả hai cùng tồn tại, có quan hệ qua code_snapshot_id.

**Định nghĩa operation_type (fix C-03, B4):**

| Giá trị | Ý nghĩa |
|---------|---------|
| `INSERT` | Chèn text mới tại vị trí (range_length = 0, text = nội dung chèn) |
| `DELETE` | Xóa đoạn text (text = rỗng, range_offset + range_length = vùng xóa) |
| `REPLACE` | Thay thế đoạn text (range_offset + range_length = vùng cũ, text = nội dung mới) |

**Định nghĩa input_source (optional metadata, không bắt buộc V1):**

| Giá trị | Ý nghĩa |
|---------|---------|
| `KEYBOARD` | Nhập bàn phím |
| `PASTE` | Dán (Ctrl+V hoặc chuột phải) |
| `AUTOCOMPLETE` | Gợi ý IDE |
| `UNKNOWN` | Không xác định |

> Paste là input mechanism, KHÔNG phải operation_type. Kết quả dữ liệu của paste vẫn là INSERT hoặc REPLACE.

**Trường của EDITOR_CHANGE:**

| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `operation_type` | Enum | INSERT \| DELETE \| REPLACE |
| `range_offset` | int | Vị trí ký tự bắt đầu (0-indexed) |
| `range_length` | int | Độ dài vùng bị ảnh hưởng (0 với INSERT thuần) |
| `text` | string | Nội dung được chèn/thay thế (rỗng với DELETE) |
| `editor_version` | string | State/version identifier của editor để hỗ trợ replay |
| `input_source` | Enum (optional) | KEYBOARD \| PASTE \| AUTOCOMPLETE \| UNKNOWN |

**Trường chung của mọi event:**

| Trường | Mô tả |
|--------|-------|
| `id` | UUID |
| `session_id` | Foreign key |
| `event_type` | Enum |
| `client_timestamp` | Ghi nhận nhưng không phải authoritative source |
| `server_timestamp` | Authoritative — do server tạo khi nhận event |
| `sequence_number` | **1-based**, monotonic tăng dần, per session — chống duplicate. First event = 1. Không chấp nhận 0 hoặc negative. (fix Mi-NEW-04) |

#### 1.7.3 Code Snapshot

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **CodeSnapshot** | id, session_id, content, language, loc, created_at, trigger_reason | Immutable sau khi tạo |
| **TriggerReason** | RUN \| SUBMIT \| CHECKPOINT | |

**Quy tắc domain:**
- Snapshot KHÔNG được tạo mỗi phím gõ.
- Snapshot được tạo: khi RUN, khi SUBMIT, tại checkpoint định kỳ.
- Snapshot là immutable. Không update sau khi lưu.
- Run phải tham chiếu snapshot tồn tại (DTI-05).
- Submission phải tham chiếu final snapshot hợp lệ nếu source đã được server nhận (DTI-06).

#### 1.7.4 Idle Detection

| Concept | Định nghĩa |
|---------|-----------|
| **Idle interval** | Khoảng thời gian giữa hai meaningful event liên tiếp |
| **Idle threshold** | >= 5 phút không có meaningful event (configurable) |
| **Idle attention signal** | Khi idle interval >= threshold |

**Meaningful event** (dùng để tính idle):
- `EDITOR_CHANGE`
- `RUN_EXECUTED`
- `SUBMISSION_MADE`

**Quy tắc domain:**
- Idle chỉ là attention signal với factual evidence.
- Idle KHÔNG được dùng để kết luận học sinh không hiểu bài.
- Idle KHÔNG được diễn giải tự động. TEACHER là người diễn giải.
- Idle có thể có nhiều lý do: tư duy, đọc tài liệu, vấn đề kỹ thuật, v.v.
- Wording trong evidence phải là factual: "Không ghi nhận meaningful activity trong N phút." — KHÔNG PHẢI "Học sinh gặp khó khăn."

---

### 1.8 Attention Signal

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **AttentionSignal** | id, student_id, session_id, signal_type, evidence (JSON), rule_version, detected_at, status | teacher_note đã bị LOẠI BỎ (fix CON-01, M-07, B7) |
| **SignalType** | IDLE_DETECTED \| LOC_ANOMALY \| REPEATED_FAILURE \| FAST_FIRST_CODE | **V1 closed enum (fix Mi-NEW-02).** Chỉ mô tả hiện tượng observable. Không dùng "..." |
| **SignalStatus** | NEW \| ACKNOWLEDGED \| DISMISSED | |

**evidence JSON schema per SignalType (V1 closed):**

| SignalType | Evidence Schema | Configurable Threshold |
|------------|----------------|------------------------|
| `IDLE_DETECTED` | `{start_time, end_time, duration_seconds, meaningful_event_before_id, threshold_used}` | idle_threshold_minutes |
| `LOC_ANOMALY` | `{session_id, final_loc, context_median_loc, delta, threshold_relative}` | relative (no absolute) |
| `REPEATED_FAILURE` | `{problem_id, submission_count, failed_count, verdicts[], time_range_start, time_range_end}` | min failed_count configurable |
| `FAST_FIRST_CODE` | `{problem_open_time, first_code_event_time, delta_seconds, threshold_seconds}` | threshold_seconds configurable |

**Quy tắc domain:**
- Signal chỉ mô tả **hiện tượng observable** + **bằng chứng** (event IDs, timestamps, values).
- Signal KHÔNG chứa nhận định: "gian lận", "không hiểu", "yếu", "có vấn đề", "đáng ngờ".
- Signal evidence KHÔNG được TEACHER sửa (chỉ đọc).
- TEACHER là người duy nhất có quyền diễn giải signal.
- LOC anomaly chỉ là signal tương đối, không có absolute threshold cố định.
- `rule_version` ghi lại phiên bản algorithm sinh signal — để reproducibility.
- Một Signal có thể có 0..N TeacherAnnotations.

---

### 1.9 Teacher Annotation (Ghi chú đánh giá)

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **TeacherAnnotation** | id, teacher_id, student_id, session_id (nullable), signal_id (nullable), content, created_at, updated_at | |

**CRUD semantics (fix M-08, B12):**

| Action | Điều kiện |
|--------|-----------|
| CREATE | TEACHER tạo annotation về học sinh thuộc lớp mình |
| READ (list) | TEACHER xem annotation do chính mình tạo, filter theo student/session/signal |
| UPDATE | Chỉ TEACHER đã tạo annotation đó mới sửa được |
| DELETE | Chỉ TEACHER đã tạo annotation đó mới xóa được |

**Quy tắc domain:**
- Ghi chú là quan điểm chủ quan của TEACHER, không phải kết luận của hệ thống.
- TEACHER chỉ ghi chú về học sinh trong lớp mình.
- TEACHER không được sửa/xóa annotation của TEACHER khác.
- Signal evidence (AttentionSignal.evidence) không được sửa qua TeacherAnnotation.
- Annotation có thể tham chiếu: student (bắt buộc) + session (optional) + signal (optional).

---

### 1.10 Audit Log

| Entity | Thuộc tính cốt lõi | Ghi chú |
|--------|-------------------|---------|
| **AuditLog** | id, actor_id, actor_role, action, target_type, target_id, detail (JSON), ip_address, user_agent, timestamp | |

**Quy tắc domain:**
- Audit log là append-only.
- Không log: password, access_token, refresh_token.
- Audit log là tài liệu quan trọng cho ADMIN — chỉ ADMIN được đọc.
- Ngay cả no-op action (ví dụ: đặt role giống role cũ) phải được ghi với action rõ ràng (fix Mi-01).

---

## 2. Domain Relationships

```
User (TEACHER) ---owns---> Class
Class ---has many---> Enrollment ---links---> User (STUDENT)
Class ---has many---> Exam
Class <---ClassProblemPublication---> Problem (visibility=CLASS)
TEACHER ---creates---> Problem
Problem ---belongs to---> ProblemBank
Exam ---contains---> ExamProblem ---references---> Problem
STUDENT + Problem + Exam --creates--> Session [status: ACTIVE|ENDED|ABANDONED]
Session ---produces---> TraceEvent (append-only)
Session ---produces---> CodeSnapshot (on RUN/SUBMIT/CHECKPOINT)
Session ---may trigger---> AttentionSignal
Submission ---references---> CodeSnapshot
Submission ---belongs to---> Session
ExamParticipation ---tracks status of---> STUDENT in Exam
TEACHER ---writes---> TeacherAnnotation (on Student / Session / Signal)
AttentionSignal <---references--- TeacherAnnotation (0..N)
ADMIN ---reads---> AuditLog
```

---

## 3. Ubiquitous Language

| Thuật ngữ | Định nghĩa trong hệ thống |
|-----------|--------------------------|
| **Dấu vết số (Digital Trace)** | Tập hợp TraceEvent được ghi lại trong Session |
| **Session** | Một lần học sinh làm một bài (có trạng thái rõ ràng) |
| **Snapshot** | Bản chụp code tại một thời điểm (immutable) |
| **Attention Signal** | Tín hiệu hệ thống: có hiện tượng observable đáng chú ý — KHÔNG phải kết luận |
| **Meaningful Event** | Event dùng để tính idle: EDITOR_CHANGE, RUN_EXECUTED, SUBMISSION_MADE |
| **Verdict** | Kết quả chấm tự động của code runner |
| **Annotation** | Ghi chú chủ quan của TEACHER về một học sinh/session/signal |
| **Kho đề** | Problem Bank — tập hợp problem của TEACHER |
| **Kỳ thi** | Exam — tập hợp problem + thời gian + lớp |
| **NEEDS ATTENTION** | Label UI cho danh sách học sinh có AttentionSignal chưa acknowledged |
| **OBSERVATION EVIDENCE** | Dữ liệu factual trong evidence JSON của AttentionSignal |
| **Finalization** | Hành động kết thúc Exam của một STUDENT (COMPLETED) hoặc do timeout (EXPIRED) |

---

## 4. Domain Invariants (Bất biến)

| # | Invariant |
|---|-----------|
| DI-1 | TraceEvent không bao giờ bị update hoặc delete. |
| DI-2 | CodeSnapshot không bao giờ bị update sau khi tạo. |
| DI-3 | (session_id, sequence_number) là unique — chống duplicate event. |
| DI-4 | server_timestamp do server tạo tại thời điểm nhận event — không phụ thuộc client. |
| DI-5 | AttentionSignal không chứa kết luận chủ quan về học sinh. |
| DI-6 | TEACHER không truy cập dữ liệu lớp khác. |
| DI-7 | STUDENT không đọc raw trace / attention signal trong V1. |
| DI-8 | Submission trong Exam chỉ được tạo khi ExamParticipation.status = IN_PROGRESS. |
| DI-9 | Problem không bị xóa khi đang có Exam ACTIVE hoặc ONGOING chứa nó. |
| DI-10 | AttentionSignal KHÔNG chứa teacher_note — ghi chú là TeacherAnnotation riêng biệt. |
| DI-11 | Session có trạng thái rõ ràng (ACTIVE/ENDED/ABANDONED) + termination_actor. |
| DI-12 | Exam timeout được enforce SERVER-SIDE, không phụ thuộc client gửi SESSION_ENDED. |
| DI-13 | Không được mất quan hệ: Student → Session → TraceEvent → CodeSnapshot → Run → Submission. |

---

## 5. Digital Trace Invariants (DTI)

Bổ sung theo yêu cầu phân tích (B5, E section):

| DTI-ID | Invariant | Ghi chú |
|--------|-----------|---------|
| **DTI-01** | TraceEvent phải append-only — không UPDATE, không DELETE | DI-1 |
| **DTI-02** | (session_id, sequence_number) phải unique | DI-3, chống duplicate |
| **DTI-03** | server_timestamp do server tạo khi nhận event | DI-4 |
| **DTI-04** | client_timestamp không được dùng làm nguồn duy nhất cho authorization hoặc exam deadline enforcement | B5 |
| **DTI-05** | RUN_EXECUTED phải tham chiếu CodeSnapshot tồn tại (code_snapshot_id valid) | §1.7.3 |
| **DTI-06** | Submission phải tham chiếu final snapshot hợp lệ nếu server đã nhận code trước timeout | §1.6 |
| **DTI-07** | AttentionSignal phải có evidence JSON không rỗng | §1.8 |
| **DTI-08** | AttentionSignal không phải student diagnosis — chỉ là observation evidence | DI-5 |
| **DTI-09** | Idle chỉ tính từ meaningful events (EDITOR_CHANGE, RUN_EXECUTED, SUBMISSION_MADE) | §1.7.4 |
| **DTI-10** | Exam timeout được enforce server-side | DI-12 |
| **DTI-11** | TEACHER chỉ quan sát STUDENT thuộc Class mà TEACHER được authorize | DI-6 |
| **DTI-12** | STUDENT không đọc raw trace / attention signal trong V1 (OUT-OF-SCOPE) | NG10 |
| **DTI-13** | Quan hệ Student → Session → Trace → Snapshot → Run → Submission phải toàn vẹn | DI-13 |

---

## 6. Lịch sử thay đổi

| Version | Date | Thay đổi |
|---------|------|----------|
| 0.1 | 2026-09-19 | Khởi tạo |
| 0.2 | 2026-09-19 | Fixes: SessionStatus, TerminationActor, EDITOR_CHANGE operation_type enum, ExamParticipationStatus, ClassProblemPublication, AttentionSignal (remove teacher_note), TeacherAnnotation CRUD, DTI section, DI updates |
| 0.3 | 2026-09-19 | Final baseline: LanguageIdentifier CPP17\|PYTHON3 (OQ-22); SignalType closed enum IDLE_DETECTED\|LOC_ANOMALY\|REPEATED_FAILURE\|FAST_FIRST_CODE (Mi-NEW-02); ABANDONED policy≠idle (Mi-NEW-01); sequence_number 1-based (Mi-NEW-04); Practice+Exam concurrency V1 policy (Mi-NEW-05); SessionContext field |
