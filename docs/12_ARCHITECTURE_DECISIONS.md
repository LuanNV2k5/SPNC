# 12 — ARCHITECTURE DECISIONS (ADR)

## ADR-001 Modular Monolith
**Context:** Hệ thống cần đáp ứng 500-1000 concurrent sessions, logic phức tạp ở phần đánh giá trace nhưng domain về user, class, exam có sự gắn kết chặt chẽ.
**Options:** (1) Microservices; (2) Modular Monolith.
**Decision:** Chọn Modular Monolith với FastAPI.
**Reason:** Đảm bảo dễ deploy, dễ test, tránh complexity của distributed transactions.
**Consequences:** Có thể tái cấu trúc tách component (như Trace Processor) nếu scale vượt quá 10,000 sessions sau này.
**Risks:** Monolith có thể phình to nếu không kiểm soát ranh giới module.
**Rejected alternatives:** Microservices (quá over-engineering cho V1).

## ADR-002 PostgreSQL Primary Store
**Context:** Cần lưu trữ các dữ liệu có tính toàn vẹn cao (tài khoản, điểm, kỳ thi, trace events).
**Options:** (1) NoSQL (MongoDB); (2) SQL (PostgreSQL).
**Decision:** Chọn PostgreSQL.
**Reason:** Cần transaction mạnh mẽ, referential integrity cho Class, Exam, Submission. Trace events cũng lưu trong PostgreSQL sử dụng JSONB cho payload linh hoạt và indexing hiệu quả. Scale 500-1000 sessions hoàn toàn trong khả năng của PostgreSQL với connection pooling.
**Consequences:** Schema strict, migration cần quản lý chặt chẽ.
**Risks:** Trace volume (20,000 * 1000 = 20M rows/session period) có thể làm bảng to nhanh. Giải quyết bằng table partitioning theo thời gian/kỳ thi ở Phase 02.
**Rejected alternatives:** MongoDB (thiếu transaction mạnh, khó query join reporting).

## ADR-003 Redis Role
**Context:** Cần quản lý state tạm thời, pub/sub realtime, rate limiting.
**Options:** (1) Dùng Redis làm permanent store; (2) Dùng Redis làm transient store & coordination.
**Decision:** Redis chỉ dùng làm transient coordination, cache, rate limit, queue backend (Celery/RQ) và Pub/Sub backplane cho WebSocket. Dữ liệu durable của Run job phải nằm trong PostgreSQL.
**Reason:** Redis crash không được làm mất academic truth (như Run job của học sinh).
**Consequences:** Nếu Redis chết, hệ thống mất realtime notification và job queue tạm thời. Cần có cơ chế Reconciliation lấy lại các Job bị kẹt từ PostgreSQL để đẩy lại vào Redis khi Redis phục hồi.
**Risks:** Redis down làm chậm performance (do cache miss).

## ADR-004 Trace Durability Strategy
**Context:** Client gửi trace events liên tục. Yêu cầu chống mất dữ liệu khi đã ACK.
**Options:** (1) API -> Redis -> ACK -> Worker -> DB; (2) API -> PostgreSQL -> ACK.
**Decision:** API -> PostgreSQL -> ACK (Direct Durable Ingestion). Batch Ingestion là một All-or-nothing DB Transaction.
**Reason:** Với 1000 concurrent sessions, batching (e.g. 5s/batch) sinh ra ~200 TPS. PostgreSQL xử lý 200 TPS batch insert rất dễ dàng. Ghi thẳng vào DB đảm bảo ACID trước khi trả ACK.
**Consequences:** Postgres chịu write-load trực tiếp. ACK semantics: Server đã lưu bền vững batch. Bắt buộc xử lý Exact Duplicate (trả 200 OK) và Conflicting Duplicate (trả 409 Conflict, reject cả batch). Gap trong sequence sẽ được detect và server trả về `highest_contiguous_sequence` hoặc `next_expected_sequence` để client biết đường retry. Client chỉ xóa buffer khi nhận ACK thành công.
**Risks:** Nếu client gửi từng keystroke không batch, DB có thể quá tải (nhưng Use Case đã yêu cầu Client buffer batching).
**Rejected alternatives:** Dùng Redis buffer (Option 1) bị reject vì rủi ro mất dữ liệu nếu Redis crash sau khi API trả ACK nhưng Worker chưa flush vào DB.

## ADR-005 REST + WebSocket Hybrid
**Context:** Yêu cầu realtime cho Teacher quan sát, nhưng dữ liệu phải bền vững.
**Options:** (1) 100% WebSocket; (2) REST + WebSocket.
**Decision:** REST làm source of truth, WebSocket chỉ làm notification channel.
**Reason:** Giảm tải stateful connection. Khi disconnect, refetch REST đảm bảo không mất state. Không stream raw source code qua WS.
**Consequences:** Client logic phức tạp hơn chút khi phải sync lại sau reconnect.
**Risks:** Sync delay nếu tải lớn.

## ADR-006 Judge Isolation
**Context:** Chạy code do Student submit (C++, Python).
**Options:** (1) Chạy trực tiếp trên API server; (2) Chạy trong Docker container riêng; (3) Chạy trên Firecracker/gVisor worker.
**Decision:** Judge Worker riêng biệt sử dụng Container Sandbox (gVisor/Docker có giới hạn user namespace/cgroups).
**Reason:** Tuyệt đối cách ly bảo mật (Project Rule 18).
**Consequences:** Kiến trúc thêm 1 component Worker.
**Risks:** Quản lý lifecycle của container phức tạp.

## ADR-007 Snapshot Storage
**Context:** Lưu trữ CodeSnapshot khi Run/Submit.
**Options:** (1) Lưu nội dung file code trong PostgreSQL (TEXT); (2) Lưu trên S3-compatible Object Storage (MinIO).
**Decision:** Lưu trên Object Storage (MinIO) cho nội dung, PostgreSQL lưu metadata. Giao thức bắt buộc: Upload-first immutable content-addressed blob.
**Reason:** Code snapshots có thể lớn, lưu nhiều bản làm phình PostgreSQL, ảnh hưởng performance bảng chính. Giao thức Upload-first đảm bảo không bao giờ có dangling DB reference (DB trỏ tới blob không tồn tại). Blob sử dụng content-addressed key (ví dụ SHA256) đảm bảo immutability.
**Consequences:** Sau khi blob được upload thành công mới ghi metadata vào PostgreSQL. Run/Submission chỉ tham chiếu metadata đã commit.
**Risks:** Nếu upload thành công nhưng ghi DB thất bại sẽ sinh ra Orphan Blob. Cần có Orphan Cleanup Worker dọn dẹp các blob không có DB reference sau một grace period.
**Rejected alternatives:** Lưu trực tiếp trong DB (làm phình DB nhanh chóng).

## ADR-008 Attention Rule Engine
**Context:** Phát hiện Idle, Anomaly, Failure.
**Options:** (1) ML Model; (2) Heuristic/Rule-based trong API; (3) Scheduled Async Worker.
**Decision:** Scheduled Async Worker xử lý Heuristic Rule-based Engine.
**Reason:** Không dùng ML theo rule. Tính toán IDLE cần một worker quét các active session theo chu kỳ (ví dụ mỗi 1 phút).
**Consequences:** Worker cần truy cập DB đọc trace event mới nhất.

## ADR-009 Server Authoritative Exam Time
**Context:** Bắt buộc enforcing thời gian Exam.
**Options:** (1) Check trạng thái Exam.status == ONGOING; (2) Check trực tiếp start_time / end_time so với server UTC time trong mọi request vào bài thi.
**Decision:** Authorization API luôn so sánh trực tiếp server UTC now với start_time / end_time.
**Reason:** Exam.status được materialize bởi scheduler có thể trễ <= 60s. Không để lag bypass security.
**Consequences:** DB query kiểm tra time luôn lấy giá trị chính xác.

## ADR-010 Deployment Strategy
**Context:** Triển khai V1.
**Options:** (1) Kubernetes; (2) Docker Compose / Swarm.
**Decision:** Docker Compose / ECS (phù hợp scale V1).
**Reason:** Không over-engineer Kubernetes khi chưa cần thiết.
**Consequences:** Dễ setup, dễ vận hành.

## ADR-011 Realtime WebSocket Revocation
**Context:** Cần thu hồi quyền realtime ngay lập tức khi tài khoản bị LOCK hoặc mất quyền (MIN-01).
**Options:** (1) Bỏ kết nối định kỳ để re-auth; (2) Revalidate JWT định kỳ trong connection; (3) Redis PubSub lắng nghe event revocation.
**Decision:** Kết hợp Revalidate JWT định kỳ trong WebSocket connection và lắng nghe event ACCOUNT_LOCKED từ Redis PubSub để force disconnect.
**Reason:** Tránh việc một connection sống dai dẳng giữ quyền truy cập khi DB state đã thay đổi. Redis chỉ là notification channel để disconnect, authentication state nằm trong Token.
**Consequences:** Phức tạp hóa logic quản lý connection tại WebSocket server.

## ADR-012 Durable Job Reconciliation
**Context:** Run jobs có thể bị kẹt PENDING nếu Redis mất dữ liệu hoặc Judge worker crash (CRIT-01). Stale workers sống lại có thể ghi đè kết quả của authoritative worker mới (CRIT-NEW-01).
**Options:** (1) Client tự retry Run; (2) Background Reconciler quét DB và Worker dùng CAS update; (3) State trong Redis.
**Decision:** Background Reconciler Worker quét định kỳ các bảng DB tìm các Run job bị kẹt ở PENDING hoặc RUNNING quá thời gian timeout (stale) và re-enqueue vào Redis. Quá trình execution sử dụng một Fencing Token (`execution_generation` hoặc `lease_id`).
**Reason:** Lỗi hệ thống không được đổ lên đầu Student. PostgreSQL là durable state, Redis là at-least-once delivery queue.
**Consequences:** Có nguy cơ Duplicate Delivery nếu job vẫn đang chạy ngầm hoặc stale worker tỉnh dậy. Giải quyết bằng Atomic Compare-and-Set (CAS) dựa trên `execution_generation`. Khi claim job (chỉ lấy PENDING -> RUNNING), cập nhật atomic và cấp `execution_generation` mới. Normal Worker không được phép claim job đang RUNNING (chỉ có Reconciler mới được can thiệp vào stale RUNNING). Khi worker lưu kết quả, phải dùng CAS `UPDATE Run ... WHERE execution_generation = current_generation`. Nếu stale worker tỉnh dậy với generation cũ, lệnh cập nhật sẽ thất bại.
