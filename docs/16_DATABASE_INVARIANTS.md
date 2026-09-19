# 16 — DATABASE INVARIANTS

| ID | Invariant | Enforcement Level | Mechanism |
|---|---|---|---|
| DBI-001 | Trace sequence_number >= 1 | DB_ENFORCED | `ck_trace_events_sequence_positive` |
| DBI-002 | Unique (session_id, sequence_number) | DB_ENFORCED | `uq_trace_events_session_sequence` |
| DBI-003 | Trace exact duplicate vs conflict detection | DB_AND_SERVICE | DB provides `uq_trace_events_session_sequence` and `canonical_fingerprint` lookup; Service handles 409 conflict logic inside transaction. |
| DBI-004 | Trace append-only | SERVICE_ENFORCED | No UPDATE/DELETE routes implemented in API. DB retention limits actual deletion. |
| DBI-005 | Trace sequence gap allowed | DB_ENFORCED | No contiguous sequence checks in DB schema. |
| DBI-006 | CodingSession context mutually exclusive (Exam vs Practice) | DB_ENFORCED | `ck_coding_sessions_context_exclusive` |
| DBI-007 | Language is canonical (CPP17, PYTHON3) | DB_ENFORCED | `ck_coding_sessions_language_canonical` |
| DBI-008 | CodeSnapshot object key uniqueness | DB_ENFORCED | `uq_code_snapshots_object_key` |
| DBI-009 | Run references valid snapshot | DB_ENFORCED | FK `fk_runs_snapshot_id_code_snapshots` |
| DBI-010 | Normal Judge claim only PENDING -> RUNNING | SERVICE_ENFORCED | Application logic uses `UPDATE runs SET status=RUNNING WHERE status='PENDING'` |
| DBI-011 | execution_generation monotonic fencing | DB_AND_SERVICE | `ck_runs_generation_positive` and Service atomic CAS. |
| DBI-012 | Stale Worker cannot overwrite result | SERVICE_ENFORCED | Service uses `WHERE execution_generation = expected`. DB ensures atomic UPDATE 0 rows. |
| DBI-013 | Submission final snapshot valid | DB_ENFORCED | FK `fk_submissions_snapshot_id_code_snapshots` |
| DBI-014 | AttentionSignal Type closed | DB_ENFORCED | Enum/String type constraints in SQLAlchemy. |
| DBI-015 | AttentionSignal has no teacher_note | DB_ENFORCED | Column structurally omitted. Teacher notes live in `teacher_annotations`. |
| DBI-016 | TeacherAnnotation ownership | DB_ENFORCED | FK `fk_teacher_annotations_teacher_id_users` |
| DBI-017 | Exam server-time fields authoritative | DB_ENFORCED | Types use `TIMESTAMPTZ`. Constraint `end_time > start_time`. |
| DBI-018 | No destructive cascade of academic evidence | DB_ENFORCED | `ON DELETE RESTRICT` used for core owner_id and session linkages. |
