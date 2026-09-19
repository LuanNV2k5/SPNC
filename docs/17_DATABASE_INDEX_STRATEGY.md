# 17 — DATABASE INDEX STRATEGY

## Indexing Principles
All indexes are explicitly created based on intended access paths, specifically focusing on Phase 01 load targets (500-1000 concurrent sessions, 20,000 traces per session).

## 1. Authentication & RBAC
- **User Lookup**: `ix_users_username`, `ix_users_email` (UNIQUE) for fast login.
- **Role Enforcement**: `ix_users_role`, `ix_users_status` for quick active user filtering.
- **Refresh Token Revocation**: `uq_refresh_sessions_token_hash` and `ix_refresh_sessions_user_id` for instant revocation lookups.

## 2. Academic Lookups
- **Teacher Class Management**: `ix_classes_owner_id` (Teacher -> Class).
- **Class Memberships**: `uq_class_memberships_class_id_student_id` (Student <-> Class mappings).
- **Problem Ownership & Visibility**: `ix_problems_owner_id`, `ix_problems_visibility` (Teacher Problem list, Public access).
- **Exam Time Lookups**: `ix_exams_start_time`, `ix_exams_end_time`, `ix_exams_status` (Authoritative checking of active Exams).

## 3. Session & Trace
- **Student Active Session**: `ix_coding_sessions_student_id`, `ix_coding_sessions_status` (Prevent multiple active practice sessions).
- **Trace Event Ingestion**: `uq_trace_events_session_sequence` (O(1) exact duplicate check).
- **Trace Conflict Detection**: `ix_trace_events_canonical_fingerprint` (O(1) conflict validation inside batch ingestion transaction).
- **Snapshot Retrieval**: `ix_code_snapshots_session_id`, `uq_code_snapshots_object_key` (Fast lookup by object storage key).

## 4. Run & Reconciliation (CRITICAL)
- **Stale PENDING/RUNNING Detection**: `ix_runs_status` + `ix_runs_lease_expires_at`. The Reconciler uses these indexes to quickly scan for jobs needing fencing or recovery without full table scans.
- **Run Fencing History**: `ix_runs_session_id` (Fetching historical execution generation status).

## 5. Observation & Audit
- **Attention Signals**: `ix_attention_signals_session_id`, `ix_attention_signals_student_id`, `ix_attention_signals_status` (Teacher Dashboard Timeline).
- **Teacher Annotations**: `ix_teacher_annotations_teacher_id`, `ix_teacher_annotations_student_id` (Filtering by who owns the note).
- **Audit Logs**: `ix_audit_logs_timestamp`, `ix_audit_logs_actor_id`, `ix_audit_logs_action` (Admin dashboard log filtering).

## Performance Notes
- **NOT BENCHMARKED YET**: While these indexes represent the structurally correct access paths, performance over 100M+ rows of `trace_events` has not been benchmarked.
- Table partitioning for `trace_events` is deferred (Anti-overengineering) until retention policies prove insufficient to keep the main table within normal Vacuum limits.
