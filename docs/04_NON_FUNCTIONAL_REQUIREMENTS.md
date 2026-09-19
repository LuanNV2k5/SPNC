# 04 — NON-FUNCTIONAL REQUIREMENTS

> **System Name:** Digital Trace Programming Learning System (DTPLS)
> **Version:** 0.3 — Final Phase 00 Baseline (OQ-17/18/19/20/21/22 RESOLVED; Mi-NEW-03 fixed)
> **Date:** 2026-09-19
> **Status:** DRAFT

---

## Lưu ý quan trọng

Tài liệu này phản ánh baseline đã được stakeholder phê duyệt.  
**7 BLOCKING_ARCHITECTURE OQs đã được RESOLVED** — xem [OPEN_QUESTIONS.md](./OPEN_QUESTIONS.md).  
Các con số capacity/performance là engineering targets và planning assumptions, không phải hard limits.

---

## NFR-1: Performance (Hiệu năng)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-PERF-001** | API phản hồi (CRUD thông thường) < 300ms ở P95 | SHOULD | Không bao gồm code execution |
| **NFR-PERF-002** | API ingest trace event batch < 500ms ở P95 | MUST | Critical path khi học sinh làm bài |
| **NFR-PERF-003** | Tải timeline trace của một session < 2s ở P95 | SHOULD | Tải toàn bộ events của session |
| **NFR-PERF-004** | Code runner trả kết quả Run (sample test) < 5s | MUST | Sau khi nhận request |
| **NFR-PERF-005** | Code runner trả kết quả Submit (hidden tests) < 30s | SHOULD | Phụ thuộc số test case |
| **NFR-PERF-006** | V1 capacity baseline: EXPECTED_BASELINE = 500 concurrent sessions; LOAD_TEST_TARGET = 1,000 concurrent sessions (OQ-17 RESOLVED) | SHOULD | Đây là engineering capacity target, KHÔNG phải hard business limit. Không hardcode MAX_STUDENTS = 500. Architecture phải cho phép horizontal scaling. |
| **NFR-PERF-007** | Trace ingest phải xử lý batch thay vì single event | MUST | PROJECT_RULES #27 |
| **NFR-PERF-008** | Trace capacity baseline: architecture phải xử lý được ~20,000 events per session dài (OQ-18 RESOLVED) | SHOULD | Sizing assumption, KHÔNG phải giới hạn nghiệp vụ. Không reject session vì vượt con số này. |
| **NFR-PERF-009** | Exam start/end scheduler materialization tolerance: <= 60 seconds (fix Mi-NEW-03) | SHOULD | Chỉ ảnh hưởng display/materialized ExamStatus. Authorization phải dùng authoritative start_time/end_time trực tiếp, không phụ thuộc materialized status. |

---

## NFR-2: Scalability (Khả năng mở rộng)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-SCALE-001** | Hệ thống phải hỗ trợ scale horizontal cho API server | SHOULD | Không stateful session server-side |
| **NFR-SCALE-002** | Code runner phải scale độc lập với API | MUST | Sandbox pool hoặc container orchestration |
| **NFR-SCALE-003** | Trace store phải hỗ trợ volume lớn (append-heavy write pattern) ~20,000 events/session (OQ-18 RESOLVED) | MUST | Physical partitioning/optimization quyết định trong Architecture phase sau benchmark. Không premature partitioning chỉ vì assumption này. |
| **NFR-SCALE-004** | API collection phải có pagination | MUST | PROJECT_RULES #26 |

---

## NFR-3: Reliability (Độ tin cậy)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-REL-001** | V1 deployment target: 99.5% monthly availability (OQ-19 RESOLVED) | MUST | Deployment target cho educational platform. Không bắt buộc multi-region/active-active trong V1. |
| **NFR-REL-002** | Nếu ingest trace thất bại (network), client phải retry với backoff | MUST | Client-side queue + retry; server idempotent |
| **NFR-REL-003** | Code runner crash không làm chết API | MUST | Isolation; timeout; graceful error |
| **NFR-REL-004** | Database phải có backup định kỳ (OQ-20 RESOLVED) | MUST | RPO ≤ 24 hours; RTO ≤ 4 hours |
| **NFR-REL-005** | Scheduler (tự động ONGOING/ENDED) phải chịu được server restart | MUST | Persistent job, không mất trạng thái |
| **NFR-REL-006** | Architecture phải có: health checks, graceful restart, retry hợp lý, Judge isolation, DB backup | MUST | V1 reliability baseline (OQ-19/20 RESOLVED) |
| **NFR-REL-007** | Phải backup PostgreSQL + persistent snapshot/object metadata | MUST | OQ-20 RESOLVED. Architecture cho phép nâng cấp backup policy sau. |
| **NFR-REL-008** | WebSocket khi disconnect: client phải reconnect + REST refetch/resync state (OQ-14 RESOLVED) | MUST | Database/server state là source of truth. WebSocket chỉ là notification channel. |

---

## NFR-4: Security (Bảo mật)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-SEC-001** | Mọi API nhạy cảm phải xác minh user và role | MUST | PROJECT_RULES #10 |
| **NFR-SEC-002** | Password phải hash bằng thuật toán mạnh (bcrypt / argon2) | MUST | Không lưu plain text |
| **NFR-SEC-003** | Không log password, access_token, refresh_token | MUST | PROJECT_RULES #25 |
| **NFR-SEC-004** | Code runner sandbox: không access network, filesystem ngoài scope | MUST | PROJECT_RULES #19 |
| **NFR-SEC-005** | Code học sinh không chạy trong API process | MUST | PROJECT_RULES #18 |
| **NFR-SEC-006** | Truyền dữ liệu qua HTTPS/TLS | MUST | Không plain HTTP |
| **NFR-SEC-007** | Token phải có expiry hợp lý | MUST | Access token ngắn; refresh token dài hơn |
| **NFR-SEC-008** | TEACHER không truy cập dữ liệu lớp khác — enforce tại backend | MUST | PROJECT_RULES #12 |
| **NFR-SEC-009** | STUDENT không truy cập trace của học sinh khác — enforce tại backend | MUST | PROJECT_RULES #13 |
| **NFR-SEC-010** | Rate limiting trên endpoint đăng nhập | SHOULD | Chống brute force; OQ-02 pending |
| **NFR-SEC-011** | Audit log ghi mọi hành động nhạy cảm | MUST | Append-only, không xóa |
| **NFR-SEC-012** | Input validation đầy đủ (code injection, XSS, SQL injection prevention) | MUST | Không tin input từ client |
| **NFR-SEC-013** | Exam authorization phải kiểm tra authoritative time-window trực tiếp, không chỉ materialized ExamStatus (fix Mi-NEW-03) | MUST | Scheduler lag không được trở thành authorization bypass |

---

## NFR-5: Data Integrity (Tính toàn vẹn dữ liệu)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-DATA-001** | Trace event phải append-only, không được UPDATE hoặc DELETE | MUST | PROJECT_RULES #14 |
| **NFR-DATA-002** | CodeSnapshot phải immutable sau khi tạo | MUST | Domain invariant |
| **NFR-DATA-003** | Timestamp database phải UTC | MUST | PROJECT_RULES #15 |
| **NFR-DATA-004** | Client timestamp được lưu nhưng server timestamp là authoritative | MUST | PROJECT_RULES #17 |
| **NFR-DATA-005** | sequence_number phải 1-based positive integer, unique per session (fix Mi-NEW-04) | MUST | First event = 1; 0 hoặc negative → rejected; PROJECT_RULES #28 |
| **NFR-DATA-006** | Mọi thay đổi database phải qua migration | MUST | PROJECT_RULES #4 |
| **NFR-DATA-007** | Không sửa migration cũ đã applied — tạo migration mới | MUST | PROJECT_RULES #5 |
| **NFR-DATA-008** | Default trace data retention baseline: 180 days; retention phải configurable (OQ-21 RESOLVED) | MUST | 180 days KHÔNG hardcode trong business logic; override bằng deployment policy; deletion phải giữ referential integrity |

---

## NFR-6: Observability (Khả năng quan sát hệ thống)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-OBS-001** | Mọi API error phải có error_code, message, request_id | MUST | PROJECT_RULES #29 |
| **NFR-OBS-002** | Hệ thống phải có structured logging (JSON logs) | SHOULD | Cho phép parse và search |
| **NFR-OBS-003** | Hệ thống phải expose health check endpoint | SHOULD | Dùng cho load balancer / k8s |
| **NFR-OBS-004** | Code runner phải log execution metrics (time, memory) | SHOULD | Debugging và tuning |

---

## NFR-7: Maintainability (Khả năng bảo trì)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-MAIN-001** | Backend phải chia: router / service / repository / model / schema | MUST | PROJECT_RULES #6 |
| **NFR-MAIN-002** | Business logic không viết trong controller/router | MUST | PROJECT_RULES #7 |
| **NFR-MAIN-003** | Frontend không truy cập database trực tiếp | MUST | PROJECT_RULES #8 |
| **NFR-MAIN-004** | Mỗi feature phải có test (unit + integration) | MUST | PROJECT_RULES #23 |
| **NFR-MAIN-005** | Không merge khi lint fail / typecheck fail / unit test fail / integration test fail | MUST | PROJECT_RULES #24 |
| **NFR-MAIN-006** | Module tiếp theo chỉ code khi module hiện tại PASS kiểm tra | MUST | PROJECT_RULES #3 |

---

## NFR-8: Usability (Khả năng sử dụng)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-USE-001** | Editor code phải hỗ trợ syntax highlighting cho CPP17 và PYTHON3 (OQ-22 RESOLVED) | SHOULD | V1 languages |
| **NFR-USE-002** | Timeline trace phải dễ đọc theo chronological order | MUST | TEACHER là người dùng chính |
| **NFR-USE-003** | AttentionSignal phải hiển thị evidence rõ ràng, không dùng từ ngữ phán xét | MUST | Domain invariant |
| **NFR-USE-004** | Thời gian còn lại của kỳ thi phải hiển thị real-time cho STUDENT | SHOULD | |
| **NFR-USE-005** | Teacher dashboard phải hỗ trợ realtime update qua WebSocket cho session status + signal notification (OQ-14 RESOLVED) | SHOULD | WebSocket notification only; không stream source code; REST là primary data source |

---

## NFR-9: Compliance & Ethics (Tuân thủ & Đạo đức)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-ETH-001** | Hệ thống KHÔNG được kết luận học sinh gian lận dựa trên trace | MUST | Core principle |
| **NFR-ETH-002** | Hệ thống KHÔNG được kết luận học sinh không hiểu bài hoặc yếu | MUST | Core principle |
| **NFR-ETH-003** | LOC anomaly không được dùng absolute threshold như kết luận khoa học | MUST | Core principle |
| **NFR-ETH-004** | Idle signal không được diễn giải tự động thành kết luận | MUST | Core principle |
| **NFR-ETH-005** | Giáo viên là người duy nhất diễn giải dấu vết | MUST | Core principle |
| **NFR-ETH-006** | Dữ liệu trace của học sinh chỉ được dùng cho mục đích giáo dục trong hệ thống; V1 privacy engineering baseline — not a certification of GDPR compliance (OQ-21 RESOLVED) | MUST | Data minimization; least privilege; audit access |

---

## NFR-10: Realtime Architecture (Kiến trúc realtime — OQ-14 RESOLVED)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-REALTIME-001** | V1 dùng REST cho initial load và historical data; WebSocket cho lightweight realtime notification | MUST | REST = primary; WS = notification channel only |
| **NFR-REALTIME-002** | WebSocket KHÔNG stream raw source code mỗi keystroke tới Teacher | MUST | Source code chỉ qua Trace Ingestion pipeline và REST API |
| **NFR-REALTIME-003** | WebSocket là notification channel; database/server state là source of truth | MUST | Client phải REST refetch sau WS disconnect + reconnect |

---

## NFR-11: Judge Architecture (Kiến trúc Judge — OQ-22 RESOLVED)

| ID | Requirement | Priority | Ghi chú |
|----|-------------|----------|---------|
| **NFR-JUDGE-001** | V1 Judge chính thức hỗ trợ CPP17 (GCC-compatible C++17) và PYTHON3 (Python 3.x) | MUST | Không implement ngôn ngữ khác V1 |
| **NFR-JUDGE-002** | Judge architecture phải extensible để thêm language adapter sau V1 | SHOULD | Plugin/adapter pattern; không hardcode compiler path |
| **NFR-JUDGE-003** | Compiler/runtime version cụ thể là deployment configuration, không hardcode vào domain requirement | MUST | Chỉ compatibility contract: CPP17, PYTHON3 là canonical identifiers |

---

## Changelog

| Version | Date | Thay đổi |
|---------|------|----------|
| 0.1 | 2026-09-19 | Khởi tạo |
| 0.2 | 2026-09-19 | Fix Mi-06: NFR-PERF-006 MUST → SHOULD |
| 0.3 | 2026-09-19 | Final baseline: +NFR-PERF-008/009 (OQ-18, Mi-NEW-03); Update NFR-PERF-006 (OQ-17); Update NFR-REL-001/004 (OQ-19/20); +NFR-REL-006/007/008 (OQ-19/20/14); Update NFR-DATA-005 (Mi-NEW-04); +NFR-DATA-008 (OQ-21); Update NFR-USE-001/+005 (OQ-22/14); Update NFR-ETH-006 (OQ-21); +NFR-SEC-013 (Mi-NEW-03); +NFR-10 Realtime (OQ-14); +NFR-11 Judge (OQ-22) |
