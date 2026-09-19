# 09 — DATA FLOW ARCHITECTURE

## 1. Digital Trace Ingestion Flow

- **Direct Durable Persistence:** API ghi thẳng batch vào PostgreSQL bằng All-or-nothing DB Transaction trước khi trả ACK (ADR-004).
- **Idempotency & Duplicate Protection:** API so sánh `(session_id, sequence_number)` và canonical payload fingerprint. 
  - **Exact Duplicate:** Payload giống hệt -> Trả 200 OK (Idempotent success), không insert mới.
  - **Conflicting Duplicate:** Payload khác nhau -> Reject toàn bộ batch (HTTP 409 Conflict). Client không được xóa buffer, phải reconcile.
- **Out of Order & Gaps:** Server lưu as-is. Tuy nhiên, Server phải detect gaps và trả về `highest_contiguous_sequence` hoặc `next_expected_sequence` trong payload của ACK. 
- **Client Buffer Release Rule:** Client CHỈ được xóa local buffer khi Server trả về ACK (200 OK) xác nhận đã lưu thành công các event đó.

```mermaid
sequenceDiagram
    participant C as Student Browser
    participant API as FastAPI
    participant DB as PostgreSQL
    
    C->>C: Typings... buffer events
    C->>API: POST /traces {events: [101, 102, 103]}
    API->>API: Authenticate & Authorize
    API->>DB: BEGIN Transaction
    Note over API,DB: Check Canonical Fingerprint
    alt Exact Duplicate
        API->>DB: Ignore duplicate event
    else Conflicting Duplicate
        API->>DB: ROLLBACK
        API-->>C: 409 Conflict (Client keeps buffer)
    else New Valid Events
        API->>DB: INSERT INTO trace_events
    end
    API->>DB: COMMIT
    DB-->>API: Success
    API-->>C: 200 OK (highest_contiguous_sequence)
```

## 2. Run / Submit Execution Flow
```mermaid
sequenceDiagram
    participant S as Student
    participant API
    participant S3 as MinIO
    participant DB as PostgreSQL
    participant Q as Redis Queue
    participant W1 as Judge Worker 1
    participant Rec as Background Reconciler
    participant W2 as Judge Worker 2
    
    S->>API: POST /runs {source_code}
    Note over API,S3: 1. Snapshot Consistency Protocol
    API->>S3: Upload Immutable Content-Addressed Blob
    S3-->>API: success (object_key)
    API->>DB: Create CodeSnapshot metadata
    
    Note over API,DB: 2. Durable Run Creation
    API->>DB: Create Run record (status=PENDING, execution_generation=0)
    API-->>S: 202 Accepted (run_id)
    
    Note over API,Q: 3. Transient Delivery (At-least-once)
    API->>Q: Enqueue Run Job
    
    Note over Q,W1: 4. Worker 1 Processing (Idempotent Atomic Claim)
    Q->>W1: Pull Job
    W1->>DB: Atomic Claim: PENDING -> RUNNING, generation=1
    W1->>S3: Download source
    W1->>W1: Execute with Sandbox limits... (stalls/crashes)
    
    Note over DB,Rec: 5. Durable Reconciliation & Fencing
    Rec->>DB: Scan for Stale RUNNING (lease expired)
    DB-->>Rec: stale_run_id (W1's claim is stale)
    Rec->>DB: Atomic Reclaim: RUNNING -> PENDING, generation invalidation
    Rec->>Q: Re-enqueue Job (Redis Job Loss / Stale Recovery)
    
    Note over Q,W2: 6. Worker 2 Claims & Completes
    Q->>W2: Pull Job
    W2->>DB: Atomic Claim: PENDING -> RUNNING, generation=2
    W2->>W2: Execute...
    W2->>DB: CAS Update Run (COMPLETED) WHERE generation=2
    W2->>Q: PubSub Notification: RUN_COMPLETED
    
    Note over W1,DB: 7. Stale Worker 1 Wakes Up
    W1->>DB: CAS Update Run (COMPLETED) WHERE generation=1
    DB-->>W1: 0 rows affected (Stale Result Rejected)
```

## 3. Exam Timeout Flow (Server-Authoritative)

Khi Exam hết giờ:
- Học sinh gửi POST `/submit` lúc `t = end_time + 1s`.
- API kiểm tra `end_time` (authoritative UTC).
- Mặc dù Exam.status chưa kịp cập nhật thành ENDED, API từ chối request -> `403 Forbidden` (Exam ended).
- Background Worker (chạy mỗi 30s) quét và finalize session: Tạo submission cuối từ snapshot gần nhất với `termination_actor = SYSTEM_EXAM_TIMEOUT`.

## 4. Realtime Observation Flow
- WebSocket KHÔNG stream raw source code (chỉ gửi tín hiệu ping/event id).
- Khi Teacher dashboard nhận ping qua WebSocket báo có session thay đổi, nó sẽ gọi REST API để kéo history/trace mới nhất.

```mermaid
sequenceDiagram
    participant T as Teacher Browser
    participant API
    participant DB
    participant Redis as PubSub
    
    T->>API: WebSocket Connect
    API->>Redis: Subscribe Class/Exam channel
    
    Note over API: When Student writes trace...
    API->>DB: Save Trace
    API->>Redis: Publish (session_id_updated)
    
    Redis-->>API: Event
    API-->>T: WS Event: SESSION_UPDATED
    T->>API: GET /sessions/id/traces (REST)
    API-->>T: Trace data JSON
```
