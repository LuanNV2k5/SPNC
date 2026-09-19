# 14 — DATABASE DESIGN

## 1. Overview
The database design for the Digital Trace Programming Learning System (DTPLS) Phase 02 establishes a robust, highly-concurrent, and strongly-typed persistence layer using PostgreSQL. The schema is entirely driven by Phase 00 Requirements and Phase 01 Architecture baselines.

## 2. Core Principles
- **PostgreSQL**: Serving as the primary source of truth (ADR-002).
- **Primary Keys**: UUIDs are used for almost all tables to ensure distributed identity generation and avoid enumeration attacks.
- **Timestamps**: All timestamps use `TIMESTAMPTZ` with UTC semantics to ensure correct temporal logic globally.
- **Payloads**: `JSONB` is used exclusively for unstructured payloads (Trace events, Attention evidence, System settings, Audit metadata). Core relational keys remain outside JSONB.
- **Constraints**: Database-level constraints (`CHECK`, `UNIQUE`) are utilized extensively to guarantee invariants without relying entirely on the application layer.

## 3. Key Entities and Mapping
- **Identity & RBAC**:
  - `users` (Active, Locked, Pending statuses)
  - `refresh_sessions` (Device tracking, token revocation)
- **Academic Hierarchy**:
  - `classes`, `class_memberships` (Ownership and Class boundaries)
  - `problems`, `problem_test_cases`, `problem_class_publications` (Visibility and content safe separation)
- **Exams**:
  - `exams` (Server-authoritative timestamps)
  - `exam_problems` (Deterministic ordering)
  - `exam_assignments`
  - `exam_participations` (Aggregate tracking)
- **Coding & Traces**:
  - `coding_sessions` (Contextual association with Exam/Practice)
  - `trace_events` (Append-only, canonical fingerprinting, idempotent insertion)
  - `code_snapshots` (Immutable reference to Object Storage)
- **Judge & Submission**:
  - `runs` (Fencing via `execution_generation`, atomic CAS states)
  - `submissions` (Final graded attempts)
- **Observation**:
  - `attention_signals` (Factual evidence without opaque ML judgments)
  - `teacher_annotations` (Owned notes separate from signals)

## 4. Trace Identity and Batching Strategy
Trace ingestion operates on a batch, all-or-nothing transactional basis (ADR-004).
Each `trace_events` row enforces idempotency through the `(session_id, sequence_number)` unique constraint. The `canonical_fingerprint` ensures exact duplicate vs conflicting duplicate detection within the transaction before commit.

## 5. Judge Fencing (execution_generation)
The `runs` table tracks job state (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED_INTERNAL`).
Stale-worker fencing is enforced via `execution_generation`. Any claim (Normal or Reconciler) uses an atomic state transition in PostgreSQL, bumping the generation. Workers persist results via CAS (`UPDATE runs ... WHERE execution_generation = current`).

## 6. Retention & Clean-up
Academic entities are designed around Deactivate/Archive patterns (e.g. `is_active` on Class) rather than hard-delete. Trace event retention is configurable and managed by a background cleanup strategy, not through cascading deletes that could destroy submission evidence.
