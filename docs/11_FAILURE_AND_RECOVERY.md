# 11 — FAILURE AND RECOVERY

## F01. PostgreSQL Unavailable
- **Impact:** Toàn bộ hệ thống (Login, Trace Ingest, Run, Teacher View) đều bị lỗi 5xx.
- **Detection:** Health check `/health/ready` fail, trigger alert.
- **Data-loss risk:** Trace đang ở in-flight request chưa ACK sẽ bị lỗi. Trách nhiệm client (Monaco) phải buffer lại và retry. Trace đã ACK không mất.
- **Recovery:** Restart DB. Nếu DB hỏng, restore từ backup (RPO 24h, RTO 4h).

## F02. Redis Unavailable
- **Impact:** Mất WebSocket realtime, không thể enqueue Run job. Cache miss gây chậm hệ thống.
- **Detection:** Timeout khi connect Redis, alert.
- **Data-loss risk:** Không mất permanent academic data. Dữ liệu Run lưu durable trong PostgreSQL.
- **Recovery:** Restart Redis, FastAPI tự động reconnect pubsub. Các Run job bị mất trong queue sẽ được Background Reconciler tự động quét các bản ghi PENDING trong PostgreSQL và re-enqueue. Tuyệt đối không bắt học sinh ấn Run lại.

## F03. Trace Worker Crash
- **(Lưu ý: Không dùng Trace Worker trên critical path ingest — ADR-004).**
- Nếu Background Worker (xử lý Attention Signal) crash:
- **Impact:** Không sinh IDLE_DETECTED, không materialization Exam status kịp thời.
- **Data-loss risk:** Không. Trace đã nằm trong DB.
- **Recovery:** Container restart policy. Worker sẽ chạy lại và tính toán bù.

## F04. Judge Worker Crash
- **Impact:** Các Run job đang chạy sẽ bị kén, không có kết quả trả về.
- **Data-loss risk:** Không mất code snapshot (đã lưu MinIO/DB). Tuy nhiên Run đang chạy có thể kẹt vĩnh viễn ở trạng thái RUNNING.
- **Recovery:** Background Reconciler giám sát các bản ghi có trạng thái RUNNING quá thời gian wall-clock timeout + grace period (Stale RUNNING). Khi phát hiện, Reconciler sẽ invalid `execution_generation` (ví dụ: gán generation=N+1), cập nhật atomic trạng thái về PENDING và re-enqueue vào Redis. Worker W2 mới sẽ nhận job với generation=N+1. Nếu W1 cũ (stale worker) sống lại và cố lưu kết quả, W1 sẽ dùng generation cũ (N) và lệnh Cập nhật Compare-and-Set (CAS) của nó (`UPDATE Run ... WHERE execution_generation = N`) sẽ thất bại (0 rows affected). Kết quả stale bị reject, không ghi đè lên kết quả authoritative của W2. Đây là cơ chế bảo vệ Fencing bắt buộc (CRIT-NEW-01).

## F05. Judge Container Hangs
- **Impact:** Mã độc hoặc vòng lặp vô hạn (while True) làm kẹt CPU.
- **Detection:** Worker giám sát thời gian chạy (wall-clock timeout).
- **Recovery:** Kill container sau N giây (VD: 15s). Trả verdict `TIME_LIMIT_EXCEEDED`.

## F06. Object Storage (MinIO) Unavailable
- **Impact:** Học sinh không lưu được snapshot khi ấn Run/Submit. Không xem được code cũ.
- **Data-loss risk:** Lỗi upload (trước khi ghi DB) -> Không tạo Run, client retry an toàn. Lỗi ghi DB (sau khi upload thành công) -> Sinh ra Orphan Blob, không có DB reference.
- **Recovery:** Fix storage, restart MinIO. Giao thức Upload-first đảm bảo không tạo dangling reference. Các Orphan Blobs sẽ được một Orphan Cleanup Worker định kỳ quét và xóa. Nếu DB reference tồn tại nhưng blob trên MinIO bị mất (Snapshot Missing Blob), request Run/Submit sẽ báo lỗi; cần alert và manual intervention.

## F07. WebSocket Disconnect
- **Impact:** Giáo viên không nhận được tín hiệu realtime.
- **Data-loss risk:** Không.
- **Recovery:** Browser tự động reconnect. Sau khi reconnect, Teacher App phải gọi REST API để lấy latest state (Resynchronization).

## F08. API Restart
- **Impact:** Các request in-flight bị drop (502). Mất WebSocket connections.
- **Recovery:** NGINX trỏ sang node khác (khi scale >1), hoặc client retry HTTP. WebSocket tự reconnect.

- **Impact:** Client gửi trùng batch do network retry hoặc lỗi logic.
- **Recovery:** API dùng canonical payload fingerprint và `(session_id, sequence_number)` để kiểm tra. 
  - Exact Duplicate: Trả 200 OK (idempotent).
  - Conflicting Duplicate: Trả 409 Conflict, reject toàn bộ batch (Transaction Rollback). Client tự đối chiếu lại buffer. Không ghi đè event cũ, không bỏ qua lỗi ngầm (silently DO NOTHING).

## F10. Out-of-order Trace
- **Impact:** Client bị lỗi gửi batch, batch chứa sequence 105 đến trước khi sequence 104 có mặt.
- **Recovery:** Server ghi nhận batch out-of-order nhưng phát hiện Gap. Server trả về ACK chứa `highest_contiguous_sequence` hoặc `next_expected_sequence` (ví dụ 104). Client biết và sẽ gửi lại sequence 104. Dữ liệu cuối cùng được đảm bảo toàn vẹn. Replay chỉ được coi là hoàn chỉnh khi không còn Gap.

## F11. Browser Offline
- **Impact:** Học sinh gõ code offline.
- **Recovery:** Monaco Editor plugin buffer các trace event locally (IndexDB / memory). Khi mạng có lại, gửi bulk request lên Server.

## F12. Exam Timeout while Browser Offline
- **Impact:** Học sinh offline, quá giờ Exam end_time, sau đó reconnect.
- **Recovery:** Khi reconnect, gửi bulk trace cũ lên. API từ chối nếu timestamp nhận được > end_time + tolerance, HOẶC API nhận nhưng ghi nhận `out_of_time=true` (phụ thuộc detail implementation). Tuy nhiên, Background Worker đã chốt sổ (Finalize) ở đúng giờ, tạo Submission tự động từ snapshot gần nhất server có.

## F13. Queue Backlog
- **Impact:** Hàng nghìn học sinh ấn Run cùng lúc. Queue Judge phình to.
- **Recovery:** Tự động scale Judge Workers (nếu có auto-scaling), hoặc học sinh phải đợi lâu (trạng thái PENDING). Không sập API server.

## F14. Disk/Storage Pressure
- **Impact:** PostgreSQL hoặc MinIO đầy ổ cứng. Write fail.
- **Recovery:** Monitor & alert (70%, 80% usage). Chạy retention policy xóa trace cũ (> 180 days).

## F15. WebSocket Authorization Revoked
- **Impact:** Tài khoản Teacher bị khóa hoặc bị tước quyền theo dõi Class nhưng đang giữ connection WebSocket mở.
- **Detection:** Event ACCOUNT_LOCKED từ Redis PubSub hoặc quá trình revalidate định kỳ JWT của WebSocket connection phát hiện token invalid.
- **Recovery:** WebSocket server force disconnect các kết nối không còn quyền. Reconnect phải thực hiện Authentication & Authorization lại. Redis không làm source of truth về quyền, chỉ làm kênh trigger.
