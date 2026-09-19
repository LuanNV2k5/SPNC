# 18 — DATABASE RETENTION AND CLEANUP

## 1. Trace Event Accumulation
The `trace_events` table is the highest-volume entity in the system. A single CodingSession can generate 20,000+ rows. To avoid database bloat and performance degradation, data must be eventually archived or deleted.

## 2. Conceptual Cleanup Strategy (CRITICAL)
- **NO CASCADING DELETION OF ACADEMIC EVIDENCE**: Deleting a `User` or `Class` MUST NOT trigger a `CASCADE` delete that destroys historical trace events, code snapshots, runs, or submissions, as these represent factual academic history.
- **RESTRICT Keys**: Core identity relationships (`student_id` in `coding_sessions`, `snapshot_id` in `runs` and `submissions`) use `ON DELETE RESTRICT` or `ON DELETE SET NULL`.
- **Soft Deletes vs Status**: System uses explicit statuses (`is_active = false` or `status = 'ABANDONED'`) instead of adding universal `deleted_at` columns, maintaining schema clarity.

## 3. Recommended Periodic Maintenance
(To be implemented in Phase 05 / Ops)
- **Orphaned Refresh Tokens**: A cron job should routinely `DELETE FROM refresh_sessions WHERE expires_at < CURRENT_TIMESTAMP`.
- **Stale PENDING Runs**: The Reconciler daemon handles fencing and re-queuing of stale jobs, preventing runaway `PENDING` states.
- **Audit Logs**: Retention configured to 90 days. Older rows exported to cold storage and dropped.
- **Trace Archive**: After an academic year completes, `trace_events` for closed `classes` are exported to parquet/cold storage and deleted from PostgreSQL. This is safe because `submissions` and `runs` hold the final grades and verdicts independently of the raw keystroke traces.
