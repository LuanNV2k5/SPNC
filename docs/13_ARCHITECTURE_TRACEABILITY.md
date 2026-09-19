# 13 — ARCHITECTURE TRACEABILITY

## 1. Mapping Requirements to Decisions

| Requirement / NFR | System Component | Architecture Decision (ADR) |
|-------------------|------------------|-----------------------------|
| **V1 expected active sessions = 500; Target = 1000** | FastAPI, PostgreSQL, Worker | ADR-001 (Modular Monolith), ADR-002 (PostgreSQL) |
| **Trace assumption ~20,000 events/session** | FastAPI, PostgreSQL | ADR-004 (Direct DB Trace Ingestion) |
| **Realtime Teacher View, not raw stream** | WebSocket, Redis, FastAPI | ADR-005 (REST+WS Hybrid), ADR-003 (Redis Role) |
| **Uptime 99.5%, RPO 24h, RTO 4h** | PostgreSQL, MinIO, Docker | ADR-010 (Deployment Strategy) |
| **Code Runner Isolated (Security)** | Judge Worker, Sandbox | ADR-006 (Judge Isolation) |
| **No auto-conclusion of cheating/weakness** | Background Worker (Signal) | ADR-008 (Attention Rule Engine - Heuristic) |
| **Exam timing is server-authoritative** | FastAPI Authorization Layer | ADR-009 (Server Authoritative Exam Time) |
| **Raw Trace Retention 180 days** | Database, Retention Cron | DB retention mechanism/policy |
| **Trace Idempotency & Batch Atomicity** | FastAPI, PostgreSQL | ADR-004 (Direct DB Trace Ingestion) |
| **Trace Sequence Gaps** | FastAPI | ADR-004 (Gap Detection ACK) |
| **Run Reconciliation (Durable Job Recovery)** | Background Reconciler Worker | ADR-012 (Durable Job Reconciliation) |
| **Snapshot Consistency** | FastAPI, MinIO, PostgreSQL, Orphan Cleanup Worker | ADR-007 (Upload-first Immutable Blob) |
| **WebSocket Revocation** | WebSocket Server, Redis PubSub | ADR-011 (Realtime WebSocket Revocation) |
| **Judge Stale-worker Fencing** | Judge Worker, Reconciler, PostgreSQL | F04 Failure Recovery, `run_fencing_rejection_total` |
| **Distributed Integrity Observability** | Monitoring Infrastructure, All Modules | `07_SYSTEM_ARCHITECTURE.md` (Observability Section) |

## 2. Open Questions Review & Disposition

Dưới đây là disposition của kiến trúc đối với các Open Questions chưa được quyết định (còn OPEN trong `OPEN_QUESTIONS.md`):

- **OQ-01 (Session policy/abandoned):** DEFERRED. Code/DB xử lý trạng thái này, không ảnh hưởng cấu trúc topology.
- **OQ-02 (Login rate limit):** DEFERRED. Triển khai cấu hình ở Redis hoặc NGINX (không đổi topology).
- **OQ-03 (Email notification):** DEFERRED. Service layer xử lý gửi mail qua external SMTP, không ảnh hưởng cốt lõi.
- **OQ-04 (ADMIN locking):** DEFERRED. Business rule.
- **OQ-05 (ADMIN role change):** DEFERRED. Business rule.
- **OQ-06 (Other thresholds):** DEFERRED. DB configuration.
- **OQ-07 (Class name duplicate):** DEFERRED. DB constraint.
- **OQ-08 (TEACHER approve enroll):** DEFERRED. Workflow logic.
- **OQ-09 (No testcase problem):** DEFERRED. Validation logic.
- **OQ-10 (Problem visibility):** DEFERRED. RBAC logic.
- **OQ-11 (Exam publish validation):** DEFERRED. Validation logic.
- **OQ-12 (Assign practice to class):** DEFERRED. Data model linking.
- **OQ-13 (Client buffer capacity):** DEFERRED. Client-side implementation.
- **OQ-15 (Submission result view):** DEFERRED. Permission rule.
- **OQ-16 (Student History View):** DEFERRED. UI/API view.
- **OQ-23 (Emergency Cancel ONGOING):** DEFERRED. State machine rule.
- **OQ-24 (Cross-teacher problem reuse):** DEFERRED. Query filtering.

TẤT CẢ các câu hỏi OPEN đều thuộc về business rules (logic) hoặc feature details.
**KHÔNG CÓ CÂU HỎI NÀO BLOCK ARCHITECTURE CORE VÀ TOPOLOGY.**
Kiến trúc V1 (ADR-001 -> ADR-010) cung cấp đủ nền tảng để implement bất kỳ quyết định nào cho các OQ trên.
