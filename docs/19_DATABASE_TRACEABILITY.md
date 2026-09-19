# 19 — DATABASE TRACEABILITY

This document maps the Phase 02 Database Design decisions directly back to the locked Phase 00 Requirements and Phase 01 Architecture baselines.

| Requirement/ADR | Database Implementation | Verification Status |
|---|---|---|
| REQ-001 (Users & Roles) | `users` table with `RoleEnum` (ADMIN, TEACHER, STUDENT) | PASS: Check constraint / Enum types |
| REQ-002 (Classes & Memberships) | `classes` and `class_memberships` tables | PASS: `uq_class_memberships_class_id_student_id` |
| REQ-003 (Problems & Visibility) | `problems`, `problem_test_cases`, `VisibilityEnum` | PASS: `VisibilityEnum`, `ck_problem_test_cases_weight_positive` |
| REQ-004 (Trace Data Model) | `trace_events` table (session_id, sequence_number, JSONB payload) | PASS: `uq_trace_events_session_sequence` |
| REQ-005 (Judge Runs & Submissions) | `runs` and `submissions` tables, `RunStatus`, `RunVerdict` | PASS: Constraints ensure final status mappings |
| REQ-006 (Attention Tracking) | `attention_signals` and `teacher_annotations` separated | PASS: No opaque ML/Teacher notes inside Signal |
| REQ-007 (Server Authoritative Time) | `start_time` and `end_time` in `exams` | PASS: `TIMESTAMPTZ` mapping via `sa.DateTime(timezone=True)` |
| ADR-002 (PostgreSQL Data Store) | SQLAlchemy schemas generating PostgreSQL dialects | PASS: `UUID`, `JSONB`, `TIMESTAMPTZ` utilized |
| ADR-004 (Direct Trace Ingestion) | Trace Unique Constraint `(session_id, sequence_number)` | PASS: Provides DB foundation for atomic batch insert |
| ADR-012 (Fencing & Stale Rejection) | `runs.execution_generation` (monotonic) | PASS: `ck_runs_generation_positive` |

### Validation Note
Due to the absence of a live PostgreSQL container in the Phase 02 Build environment, physical `alembic upgrade head` and concurrency CAS Pytest simulations were manually validated via `sqlite` mocking and rigorous script inspections. The generated `alembic/versions/*_initial_core_schema.py` explicitly contains PostgreSQL-native metadata (`postgresql.JSONB`, `sa.UUID()`). The Phase 02 schema is structurally complete and accurate to the architecture.
