# 45 — RETENTION PURGE (PHASE 19 / STEP 3) SPECIFICATION

> **Module:** configurable deletion of raw trace data and expired operational rows
> **Status:** DRAFT — awaiting Project Owner approval of §6
> **Date:** 2026-10-29
> **Parent Baseline:** `phase-17-observability-locked` (`4300655`, = `main`)
> **Proposed Branch:** `phase19`
> **Target Lock Tag:** `phase-19-retention-locked`
> **Merge gate:** code that deletes data is merged only after Phase 18 (backup/restore, docs/44) is locked on `main`

---

## 1. Purpose

Step 3 of the risk-ordered plan (CI → observability + backup → retention purge). OQ-21 / NFR-DATA-008 fix a **default raw-trace retention of 180 days, configurable, never hard-coded, deletion keeping referential integrity**. Nothing deletes raw trace data today, so `trace_events` (20 000+ rows per session, docs/18 §1) and snapshot blobs grow without bound.

This phase adds one purge mechanism that:
- deletes **raw trace data** of sessions that ended more than the retention period ago;
- removes **expired refresh tokens** (docs/18 §3);
- never touches **academic records** (sessions, submissions, runs, scores, grades, participations, points), **audit logs**, or anything under a **retention hold**;
- is dry-run by default, audited, metered (Phase 17) and safe to re-run.

PostgreSQL stays the academic source of truth; the purge only removes data the policy says is no longer needed.

---

## 2. Findings (2026-10-29)

| # | Finding | Evidence | Impact |
|---|---|---|---|
| F1 | Only one retention period is decided: **raw detailed trace = 180 days**, configurable, deployment policy may override. "Aggregated academic/submission records: theo policy của đơn vị triển khai" — no period. | `OPEN_QUESTIONS.md` OQ-21; NFR-DATA-008 (`docs/04` l.91); `docs/06` §7 | Raw trace is the only class with a mandated default |
| F2 | docs/18 §3 (pre-implementation, "Phase 05 / Ops") recommends: delete expired `refresh_sessions`; audit logs 90 days then export to cold storage and drop; export `trace_events` of closed classes to parquet after the academic year. None is implemented; no export pipeline or cold storage exists. | `docs/18` §3 | docs/18's audit 90 days and parquet export conflict with "no export infrastructure" and with OQ-21's 180 days |
| F3 | An admin setting `retention_days` exists since Phase 04 (`GET/PATCH /api/v1/admin/settings`, range 1–3650, **default 30** when unset, audit `SYSTEM_SETTING_CHANGED`) but **nothing reads it**. Its default contradicts the 180-day baseline. | `services/system_settings.py:38-57`; tests `test_admin.py:354-373`, `test_phase13b_idle_threshold.py:43` | A purge wired to it unchanged would delete after 30 days |
| F4 | Raw trace data per session: `trace_events`, `scratchpad_revisions`, `code_snapshots` (+ MinIO blob, key `snapshots/{session}/{sha256}.txt`, shared by rows of one session with equal content, docs/39 D1). All three FK `coding_sessions` with `ON DELETE CASCADE`. | `models/trace.py` | Deleting per session is natural; deleting the session row would cascade into evidence (forbidden, docs/18 §2) |
| F5 | Snapshots referenced by `runs.snapshot_id`, `submissions.snapshot_id` (both `RESTRICT`) or `coding_sessions.final_code_snapshot_id` (`RESTRICT`) are the code behind a verdict/grade. Only unreferenced snapshots (mostly `CHECKPOINT`) are raw trace. | `models/run_submit.py`, `models/session.py` | The FKs already make deleting graded code impossible; the purge must select only unreferenced snapshots |
| F6 | `trace_signal_outbox.event_id → trace_events` is `RESTRICT`; rows are deleted by the signal materializer once processed. | `models/observation.py`, `services/judge/materializer.py:224` | A session with pending outbox rows cannot (and must not) be purged yet |
| F7 | Readers of raw trace after a session ends: teacher timeline (`GET …/sessions/{id}/timeline`), snapshot content (`…/snapshots/{id}`), `latest_activity()` for session lists, statistics. Finalization facts (`final_loc`, `working_time_seconds`, `final_code_snapshot_id`) are stored on the session row at end (Phase 08E). Signals (`attention_signals`) and teacher annotations are separate rows. | `repositories/observation.py:239`, `api/endpoints/observation.py:51-61`, `models/session.py` | After a purge the timeline is empty; the client must be able to tell "purged" from "no activity" |
| F8 | Existing cleanup: orphan-blob sweep (reconciler, hourly, grace 24 h, batch 500, deletes only blobs no row references; docs/39 D2); stale practice-session sweep (exam scheduler, `SESSION_STALE_HOURS`=24 → ABANDONED); stale run/submission re-enqueue (reconciler). None removes rows. | `services/snapshot_cleanup.py`, `exam_scheduler.py`, `reconciler.py` | The orphan sweep is a safety net for a blob left behind by a failed purge |
| F9 | `refresh_sessions` rows are never deleted (only `User` relationship cascade). `audit_logs` has no deletion either. | `models/user.py`; `grep -rn delete app` | Token table grows without bound; audit growth is small |
| F10 | No "dispute" / legal-hold concept exists in the schema. | `models/exam.py`, `models/class_org.py` | An exam under grade dispute could lose its raw trace on schedule |
| F11 | A restore from a backup taken before a purge brings purged rows back (Phase 18). | docs/44 (Phase 18) | Purge must be re-runnable after a restore and must not assume rows are gone |

### 2.1 Data classes

| Data class | Table / store | Retention today | Proposed (D1) |
|---|---|---|---|
| Raw trace events | `trace_events` | none | **purge** after `retention_days` (default 180) |
| Scratchpad revisions | `scratchpad_revisions` | none | **purge** with trace |
| Checkpoint snapshots + blobs (unreferenced) | `code_snapshots`, MinIO | none | **purge** with trace |
| Snapshots behind a run, submission or final code | `code_snapshots`, MinIO | none | keep (FK `RESTRICT`, academic evidence) |
| Sessions, runs, submissions, participations, points | `coding_sessions`, `runs`, `submissions`, `exam_participations`, `practice_attempts`, `point_transactions` | none | keep (deployment policy, no default) |
| Attention signals, teacher annotations | `attention_signals`, `teacher_annotations` | none | keep |
| Signal outbox | `trace_signal_outbox` | deleted after processing | unchanged; pending rows block the purge of their session |
| Refresh tokens | `refresh_sessions` | none | **delete** when `expires_at` is older than 7 days |
| Audit logs | `audit_logs` | none | keep (no deletion in V1) |
| Orphan blobs | MinIO | 24 h grace sweep | unchanged |

---

## 3. Scope

### 3.1 Eligibility (D1, D4)
A coding session is **eligible** when all hold:
1. `status` is `ENDED` or `ABANDONED` and `ended_at < now − retention_days`;
2. `trace_purged_at IS NULL` (not purged yet);
3. no `trace_signal_outbox` row for the session;
4. exam context: its exam is `ENDED` or `CANCELLED`, `end_time < now − retention_days`, and `retention_hold = false`;
5. `ACTIVE` sessions are never eligible.

`retention_days` is read from the existing admin setting (F3) with the default changed from 30 to **180** when unset, and a lower bound of **30** enforced by the purge (`RETENTION_MIN_DAYS`, env) so a mistyped setting cannot wipe recent data. The admin API keeps its 1–3650 validation; values below the floor are clamped by the purge and logged.

### 3.2 What a purge of one session does (D2, D6)
In one transaction per batch, with the session rows locked `FOR UPDATE SKIP LOCKED`:
1. `DELETE FROM trace_events WHERE session_id = …`;
2. `DELETE FROM scratchpad_revisions WHERE session_id = …`;
3. `DELETE FROM code_snapshots WHERE session_id = … AND id` not referenced by `runs`, `submissions` or `coding_sessions.final_code_snapshot_id` — collecting their `object_key`s;
4. `UPDATE coding_sessions SET trace_purged_at = now()`;
5. one `audit_logs` row per batch (D5);
6. **commit**.

After the commit, each collected `object_key` that **no remaining `code_snapshots` row references** is deleted from storage. A failed blob delete is counted and logged; the blob is now an unreferenced orphan and the existing orphan sweep (docs/39 D2) removes it later. Metadata never points at a deleted blob: rows go first, blobs only after the commit and only when unreferenced.

The session row, its runs, submissions, their snapshots and blobs, finalization facts, signals and annotations stay.

### 3.3 Refresh tokens (D1)
`DELETE FROM refresh_sessions WHERE expires_at < now − 7 days` in batches. An expired token is already rejected; the 7-day margin keeps recent families for reuse-detection forensics. Not audited per row (counted in the run's audit row and metrics).

### 3.4 Runner (D3)
- Service `app/services/retention.py`: `purge(db, *, apply: bool, now=None) -> dict` with per-class counts. Logic only here (PROJECT_RULES #7).
- **CLI** `python -m app.cli retention-purge` — dry run by default (counts what would be deleted, deletes nothing); `--apply` deletes. `--max-batches N` bounds one invocation.
- **Reconciler hook** `maybe_purge_retention(db)`, like `maybe_sweep_orphans`: at most once per `RETENTION_PURGE_INTERVAL_SECONDS` (default 86 400), only when `RETENTION_PURGE_ENABLED=true` (default **false**). Each tick processes at most `RETENTION_PURGE_MAX_BATCHES` (default 10) batches of `RETENTION_PURGE_BATCH_SIZE` sessions (default 100), so one cycle stays short.
- Concurrency: `FOR UPDATE SKIP LOCKED` on session rows plus `pg_try_advisory_xact_lock` on a fixed key per batch, so the CLI and the reconciler never work on the same rows; every statement is idempotent.

### 3.5 Retention hold (D4)
- Migration adds `exams.retention_hold BOOLEAN NOT NULL DEFAULT false` and `coding_sessions.trace_purged_at TIMESTAMPTZ NULL` (+ partial index `ix_coding_sessions_purge_candidates` on `ended_at WHERE trace_purged_at IS NULL`).
- `PUT /api/v1/admin/exams/{exam_id}/retention-hold` body `{"hold": true|false, "reason": str}` — ADMIN only, audit `RETENTION_HOLD_CHANGED` with `{old, new, reason}`; 404 `EXAM_NOT_FOUND`. The admin exam read includes `retention_hold`.

### 3.6 Visibility of a purge (D7)
- Teacher timeline response gains `trace_purged_at` (null until purged), so an empty timeline after a purge is distinguishable from a session with no events. Snapshot content of a purged checkpoint → existing 404.
- `latest_activity()` falls back to `ended_at` when no trace row exists (session lists keep a sensible "last active").
- `GET /api/v1/admin/settings` unchanged in shape; `retention_days` now reports 180 when unset.

### 3.7 Metrics (Phase 17, `app/core/metrics.py`)
- `retention_purge_rows_total{data_class}` — `trace_event`, `scratchpad_revision`, `code_snapshot`, `refresh_session`;
- `retention_purge_sessions_total{outcome}` — `purged`, `skipped_locked`;
- `retention_purge_blob_delete_total{outcome}` — `deleted`, `failed`;
- `retention_purge_eligible_sessions` (gauge, set by every run including dry runs);
- the reconciler's existing `spnc_daemon_*` series cover liveness.
Labels are bounded enumerations only (docs/43 §4.2).

### 3.8 Docs
`docs/RUNBOOK.md`: short subsection "Retention purge" (dry run, apply, enabling the daemon hook, hold, re-run after a restore). `docs/18` and `docs/14` are not edited (locked); this document supersedes docs/18 §3 for audit logs and trace archive.

### 3.9 Out of scope
Parquet/cold-storage export of traces (no target store exists); deleting or anonymising users, classes, sessions, submissions; audit-log expiry; table partitioning (docs/17 §4); a UI.

---

## 4. Invariants
1. No academic record is deleted: `coding_sessions`, `runs`, `submissions`, `exam_participations`, `practice_attempts`, `point_transactions`, `attention_signals`, `teacher_annotations`, `audit_logs` keep every row.
2. No snapshot referenced by a run, a submission or `final_code_snapshot_id` is deleted, and no blob referenced by any remaining `code_snapshots` row is deleted.
3. Blob deletion happens only after the row deletion has committed; a crash between the two leaves an orphan blob, never a dangling reference.
4. `ACTIVE` sessions, sessions with pending outbox rows, sessions of a non-finished exam and sessions of an exam on hold are never touched.
5. The retention period comes from configuration (admin setting, env floor); 180 appears only as a default, never as a literal in eligibility logic (NFR-DATA-008).
6. Dry run deletes nothing; the daemon hook is off unless `RETENTION_PURGE_ENABLED=true`.
7. Every applied batch writes one audit row; re-running a purge is idempotent.

---

## 5. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-19-01 | An ENDED practice session past retention loses its trace events, scratchpad revisions and unreferenced checkpoint snapshots (+ blobs); `trace_purged_at` is set; the session row, runs, submissions, their snapshots and blobs, signals and annotations are unchanged. |
| AC-19-02 | Not purged: ACTIVE session; session ended inside the window; session with a pending outbox row; exam session whose exam is not ENDED/CANCELLED or ended inside the window; exam on `retention_hold`. |
| AC-19-03 | A blob shared by a purged checkpoint and a submitted snapshot of the same content stays; a blob whose delete fails is counted (`failed`) and later removed by `sweep_orphans`; no `code_snapshots` row ever points at a missing blob. |
| AC-19-04 | Dry run returns the same counts as the following apply and changes no row; second apply purges nothing. |
| AC-19-05 | Retention from the admin setting; unset → 180; setting below 30 → clamped to 30. Admin `GET /settings` reports 180 when unset. |
| AC-19-06 | Expired refresh tokens older than 7 days are deleted; newer or valid ones stay. |
| AC-19-07 | Hold endpoint: ADMIN only (TEACHER/STUDENT 403), audit `RETENTION_HOLD_CHANGED`, 404 `EXAM_NOT_FOUND`, errors carry `{error_code, message, request_id}`. |
| AC-19-08 | Timeline of a purged session returns `trace_purged_at` and no events; `latest_activity` falls back to `ended_at`. |
| AC-19-09 | Metrics in §3.7 increase as expected; one audit row `RETENTION_PURGE` per applied batch, none for a dry run. |
| AC-19-10 | Reconciler hook runs nothing when disabled and at most once per interval when enabled; two concurrent purges never double-count. |
| AC-19-11 | Migration up/down/up on an empty database; isolated local groups green on a fresh PostgreSQL; `ci` green on the PR. |

---

## 6. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | What is purged, and after how long | (a) raw trace only (events, scratchpad, unreferenced snapshots + blobs) after `retention_days` (default 180, OQ-21), plus refresh tokens expired > 7 days; academic records and audit logs kept; (b) (a) plus audit logs after 90 days (docs/18 §3); (c) (a) plus practice runs and their snapshots | **(a)**. Only raw trace has a decided period (OQ-21); academic records are "deployment policy" with no default; audit logs are the evidence of who did what, including purges, and are small. |
| **D2** | Hard delete, anonymise or archive | (a) hard delete of the raw-trace rows and blobs, session row kept with `trace_purged_at`; (b) export to cold storage (parquet) then delete (docs/18 §3); (c) anonymise (strip payload/content, keep rows) | **(a)**. No cold store exists; backups (Phase 18, RPO 24 h) already hold the data until backup retention ends. (c) keeps the 20 000-rows-per-session bloat that is the reason for purging. (b) can be added later in front of (a). |
| **D3** | Which process runs it | (a) one service used by a CLI command (dry run default, `--apply`) **and** a reconciler hook off by default (`RETENTION_PURGE_ENABLED=false`), daily, bounded batches; (b) new daemon container; (c) CLI/cron only | **(a)**. No compose change (Phase 18 owns it); the operator can dry-run and apply by hand first, then enable the hook. (b) adds a sixth container for a daily job. |
| **D4** | What must never be purged / holds | (a) exclusions in §3.1 plus an `exams.retention_hold` flag set by ADMIN through `PUT /api/v1/admin/exams/{id}/retention-hold` (audited); (b) exclusions only, no hold; (c) never purge exam sessions at all | **(a)**. Disputes about an exam are the case where raw trace matters; a hold is cheap and auditable. (c) leaves most trace volume (exams) unbounded. |
| **D5** | Dry run and audit trail | (a) dry run by default in the CLI, reports per-class counts; one `audit_logs` row `RETENTION_PURGE` per applied batch (actor NULL = system, metadata: cutoff, counts, session ids); (b) one audit row per session; (c) logs only | **(a)**. Session ids per batch make every purge traceable at ≤ 1 row per 100 sessions. |
| **D6** | Order of rows vs blobs | (a) delete rows, commit, then delete blobs no row references; failures become orphans for the existing sweep; (b) blobs first, then rows; (c) leave blobs to the orphan sweep entirely | **(a)**. Never leaves metadata pointing at a missing blob (ADR-007 spirit). (b) can leave rows with no blob after a crash. (c) is safe but waits for the hourly sweep's 500-blob batches; (a) still falls back to it. |
| **D7** | Retention setting source and safety | (a) reuse the Phase 04 admin setting `retention_days`, unset default 30 → **180**, purge enforces env floor `RETENTION_MIN_DAYS=30`; (b) new env `TRACE_RETENTION_DAYS=180`, admin setting stays inert; (c) admin setting with no floor | **(a)**. One knob, already admin-editable and audited; the floor guards against a typo deleting recent traces. Changes one visible default (`GET /admin/settings` 30 → 180; one existing assertion in `test_phase13b_idle_threshold.py` is updated). |
| **D8** | Metrics | (a) §3.7 counters/gauge in `app/core/metrics.py`; (b) logs only | **(a)**. Same pattern as the orphan sweep (docs/43). |
| **D9** | Merge gate | (a) spec, code and tests on `phase19` now; PR merged only after `phase-18-*-locked` is on `main`; (b) merge now with the hook disabled | **(a)**, as the risk order requires: a deletion must be recoverable from a tested backup first. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before any code is written.

---

## 7. Verification Record

_Empty until implementation._
