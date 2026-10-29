# 39 — BACKEND COMPLETION: SHOULD GAPS & STORAGE HYGIENE (PHASE 13) SPECIFICATION

> **Module:** Snapshot key fix, orphan-blob cleanup, admin idle threshold, checkpoint linkage, student practice list (Phase 13)
> **Status:** APPROVED 2026-10-29 (all §7 recommendations; see PROJECT_PROVENANCE_LOG.md) — LOCKED 2026-10-29 (`phase-13-backend-complete-locked`)
> **Date:** 2026-10-29
> **Parent Baseline:** `phase12` @ `9a4bad6` (Phases 10–12 implemented, locks pending)
> **Proposed Branch:** `phase13`
> **Target Lock Tag:** `phase-13-backend-complete-locked`

---

## 1. Purpose

After Phase 12 every MUST requirement has an implementation. Phase 13 closes the remaining backend items:
- **a defect that blocks students** (F1);
- the storage hygiene that ADR-007 requires;
- the SHOULD requirements that are still missing.

REQ-STU-004 (points) stays out because OQ-16 is open. The frontend is a separate phase.

---

## 2. Findings (2026-10-29)

| # | Finding | Evidence | Impact |
|---|---|---|---|
| F1 | **Two snapshots with identical code in one session fail.** The object key is `snapshots/{session}/0_{sha256[:8]}.txt` (sequence always 0) and `code_snapshots.object_key` is UNIQUE, so the second metadata insert violates the constraint. | Reproduced: first `POST …/snapshots` → 200; second, same code → **500** `INTERNAL_ERROR` "Failed to save snapshot metadata". (docs/37 F6) | A student who runs or checkpoints unchanged code cannot create the snapshot, so cannot Run/Submit it. |
| F2 | No orphan-blob cleanup. ADR-007: an upload that succeeds before a failed metadata insert leaves a blob with no DB reference; "cần có Orphan Cleanup Worker … sau một grace period". | docs/12 ADR-007, docs/07 metrics `snapshot_orphan_cleanup_failure_total` | Storage grows with unreferenced blobs. |
| F3 | REQ-USER-007 (SHOULD): ADMIN configures `idle_threshold` (1–60 min); applies to **new** sessions; old sessions unchanged; AuditLog `CONFIG_CHANGED` with old and new values. | Threshold is the env setting `SIGNAL_IDLE_THRESHOLD_SECONDS`; `/admin/settings` only has `retention_days`. | Missing |
| F4 | REQ-TRACE-013 (SHOULD): a CHECKPOINT snapshot **and** a `SESSION_CHECKPOINT` event whose `code_snapshot_id` points to that snapshot. | Both exist as types, but ingest accepts any `SESSION_CHECKPOINT` payload; nothing links or validates them. | Partial |
| F5 | REQ-STU-001 (SHOULD): a student lists the practice problems they may access, "PUBLIC problems + CLASS problems của lớp mình". It is also how REQ-EXAM-008 (problem assigned to a class outside an exam) becomes visible to students. | Only `GET /problems/public/bank` (PUBLIC only) exists. | Missing |

Server-authored trace events cannot be inserted while a session is open, because the client owns `sequence_number` (docs/38 §2). So the server cannot write `SESSION_CHECKPOINT` itself; it can only validate what the client sends (D5).

---

## 3. Scope by Sub-phase

### 13A — Snapshot storage (F1, F2)
| Item | Detail |
|---|---|
| Key fix | New snapshots use the content-addressed key `snapshots/{session_id}/{sha256}.txt` (full hash). The UNIQUE constraint on `code_snapshots.object_key` is replaced by a plain index, so several metadata rows (e.g. two RUN snapshots of the same code) may reference one immutable blob (D1). Existing rows keep their old keys, which stay readable. |
| Orphan cleanup | A sweep (in the reconciler, at most once per `SNAPSHOT_ORPHAN_SWEEP_INTERVAL_SECONDS`) lists blobs under `snapshots/` older than `SNAPSHOT_ORPHAN_GRACE_HOURS` and deletes those no `code_snapshots` row references, in batches of `SNAPSHOT_ORPHAN_BATCH_SIZE` (D2). Errors are logged and the sweep continues. A blob that any row references is never deleted. |

### 13B — Admin idle threshold (F3)
| Item | Detail |
|---|---|
| Setting | `GET/PATCH /api/v1/admin/settings` gains `idle_threshold_minutes` (integer 1–60, default = current `SIGNAL_IDLE_THRESHOLD_SECONDS` / 60), stored in `system_settings`. A change writes AuditLog `CONFIG_CHANGED` `{key, old, new}`. |
| New sessions only | `coding_sessions.idle_threshold_seconds` is captured when a session is created (D3). The IDLE rules use the session's value. Sessions created before this phase (NULL) keep the deployment default, so their behaviour does not change. Evidence keeps `threshold_used` = the value actually applied. |

### 13C — Checkpoints and practice list (F4, F5)
| Item | Detail |
|---|---|
| Checkpoint linkage | Ingest validates every `SESSION_CHECKPOINT` event: `payload.code_snapshot_id` must be a snapshot of the same session with reason `CHECKPOINT`; otherwise 422 `CHECKPOINT_SNAPSHOT_INVALID` and the batch is refused (D5). `trace-state` returns `checkpoint_interval_seconds` (config `TRACE_CHECKPOINT_INTERVAL_SECONDS`, default 60) as the cadence clients should follow (D4). |
| Practice list | `GET /api/v1/my/practice/problems?difficulty=&language=` (STUDENT): PUBLIC problems plus CLASS problems published to a class where the student is an active member; never PRIVATE, never deleted; paginated, de-duplicated, newest first (D6). |

### 3.1 Out of scope
REQ-STU-004 (OQ-16); frontend; OQ-26 production judge isolation; data retention purge (separate from orphans).

---

## 4. Data Model Changes (new migration only)
- Drop `uq_code_snapshots_object_key`; add non-unique index `ix_code_snapshots_object_key`.
- `coding_sessions.idle_threshold_seconds` INT NULL, CHECK 60–3600.
- `system_settings` row `idle_threshold` (JSON `{"minutes": n}`), created on first PATCH.

---

## 5. Invariants
1. A blob referenced by any snapshot row is never deleted or modified.
2. Identical code in one session never fails to snapshot.
3. Changing the idle threshold never changes signals for sessions that already exist.
4. Every stored `SESSION_CHECKPOINT` references a CHECKPOINT snapshot of its own session.
5. Students never see PRIVATE, deleted, or other-class CLASS problems in the practice list.

---

## 6. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-13-01 | Two snapshots with identical code in one session both succeed (memory and MinIO backends); they share one blob; old-format keys still read. |
| AC-13-02 | Orphan sweep deletes only unreferenced blobs older than the grace period; referenced and recent blobs survive; storage errors do not stop the reconciler. |
| AC-13-03 | Admin sets `idle_threshold_minutes` (1–60; 0/61 → 422); AuditLog `CONFIG_CHANGED` has old/new; new sessions use it; existing sessions keep their value. |
| AC-13-04 | `SESSION_CHECKPOINT` with a missing, foreign-session or non-CHECKPOINT snapshot → 422; a valid one is stored; `trace-state` reports the interval. |
| AC-13-05 | Practice list returns PUBLIC + own-class CLASS problems only, filters work, no duplicates. |
| AC-13-06 | Full Phase 03–12 regression passes on fresh databases; demo stack rebuilt and E2E passes. |

---

## 7. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | Snapshot key fix (F1) | (a) content-addressed `snapshots/{session_id}/{sha256}.txt` and drop the UNIQUE constraint (rows may share a blob); (b) key per snapshot row (`…/{snapshot_uuid}.txt`), keep UNIQUE, no sharing; (c) reuse the existing row instead of inserting a new one | **(a)**. Matches ADR-007 ("content-addressed key (SHA256)"), removes the 8-hex prefix collision risk, and keeps one metadata row per snapshot event. (c) would lose the second RUN/SUBMIT event's own snapshot record. |
| **D2** | Orphan cleanup parameters | (a) reconciler sweep, grace 24 h, hourly, batch 500, hard delete of unreferenced blobs only; (b) separate daemon; (c) report only, no delete | **(a)**. ADR-007 asks for deletion after a grace period. 24 h is far beyond any upload → metadata gap. |
| **D3** | How "new sessions only" is guaranteed | (a) snapshot the threshold into `coding_sessions.idle_threshold_seconds` at creation; (b) record an effective-from timestamp and look up the setting history | **(a)**. Simple and auditable per session. |
| **D4** | Checkpoint cadence | (a) client-driven; server advertises `checkpoint_interval_seconds` (default 60) in `trace-state`; (b) server-driven (impossible: the server has no code between snapshots) | **(a)** |
| **D5** | Invalid `SESSION_CHECKPOINT` | (a) reject the batch with 422 `CHECKPOINT_SNAPSHOT_INVALID`; (b) store it and flag | **(a)**. Keeps invariant 4; trace stays verifiable (REQ-SIGNAL-003 spirit). Changes Phase 06 ingest for that type (DCR). |
| **D6** | Practice list scope | (a) PUBLIC + CLASS problems published to the student's active classes; (b) also problems of exams the student took | **(a)**. Exactly REQ-STU-001's AC; exam problems are reached through the exam. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md`, with DCRs for D1 (snapshot key format / constraint) and D5 (ingest validation). Order: 13A → 13B → 13C, each verified before the next.

---

## 8. Verification Record

### 8.1 Changes (2026-10-29)
| Sub-phase | Commit | Files |
|---|---|---|
| Approval | `eff23c1` | PROJECT_PROVENANCE_LOG (spec approval; DCRs SPNC_SNAPSHOT_CONTENT_KEY, SPNC_CHECKPOINT_LINKAGE) |
| 13A | `2aef0cd` | migration `f9b5d3e6a012`; `models/trace.py` (`object_key` index, not unique); `services/storage.py` (key `snapshots/{session}/{sha256}.txt`, `list_code_snapshots`, `delete_code_snapshot`); `services/snapshot_cleanup.py`; `reconciler.py` (`maybe_sweep_orphans`); config `SNAPSHOT_ORPHAN_*` |
| 13B | `048a824` | migration `a1c7e4f8b213`; `coding_sessions.idle_threshold_seconds`; `services/system_settings.py`; admin settings endpoint/schemas; session creation captures the threshold; `judge/signals.py` (`_idle_threshold(session)`) |
| 13C | `95a7473` | `services/trace.py` (`_validate_checkpoints`), trace-state `checkpoint_interval_seconds` (config `TRACE_CHECKPOINT_INTERVAL_SECONDS`), `GET /my/practice/problems` (repo/service/endpoint) |

### 8.2 Behaviour Notes
- **Snapshots:** identical code in one session now yields separate snapshot rows that share one blob. Old `…/0_{hash8}.txt` keys still read. The migration's downgrade re-adds the UNIQUE constraint and therefore fails once rows share a key; that is expected.
- **Orphan sweep:** reconciler loop, at most once per `SNAPSHOT_ORPHAN_SWEEP_INTERVAL_SECONDS` (3600). It lists up to `SNAPSHOT_ORPHAN_BATCH_SIZE` (500) blobs older than `SNAPSHOT_ORPHAN_GRACE_HOURS` (24) and deletes the ones no `code_snapshots.object_key` references. A listing or delete failure is logged and counted, never raised. The memory backend tracks blob creation time for this; blobs written straight into the dict by tests count as new.
- **Idle threshold:** `/admin/settings` returns `{retention_days, idle_threshold_minutes}`; PATCH takes either or both; an empty body → 422. Idle changes write `CONFIG_CHANGED` with `{key, old, new}`; retention keeps the Phase 04 `SYSTEM_SETTING_CHANGED` action. Practice and exam sessions store the value in force at creation; IDLE evidence `threshold_used` is the session's value.
- **Checkpoints:** every `SESSION_CHECKPOINT` in a batch is validated before insertion; a missing, malformed, foreign-session or non-CHECKPOINT `code_snapshot_id` → 422 `CHECKPOINT_SNAPSHOT_INVALID` and nothing from the batch is stored. `GET …/trace-state` (student) adds `checkpoint_interval_seconds`.
- **Practice list:** `GET /my/practice/problems?difficulty=&language=` (STUDENT) returns PUBLIC problems plus CLASS problems published to a class with an active membership; never PRIVATE or deleted; one row per problem; newest first.

### 8.3 Verification
| Check | Environment | Result |
|---|---|---|
| Migrations `f9b5d3e6a012`, `a1c7e4f8b213` | Empty DB, PostgreSQL 16.15 | up / down / up OK; at head `ix_code_snapshots_object_key` (no UNIQUE) and `ck_coding_sessions_idle_threshold_range` |
| 13A `test_phase13a_snapshots.py` + `tests/infra/test_storage_s3.py` | Disposable PostgreSQL 16.15 + disposable MinIO | **5 + 7 passed** (F1 regression, old keys readable, sweep keeps referenced/recent blobs, sweep survives storage errors, hourly throttle; MinIO list/delete) |
| 13B `test_phase13b_idle_threshold.py` | Disposable PostgreSQL 16.15 | **3 passed** |
| 13C `test_phase13c_checkpoint_practice.py` | same | **3 passed** |
| Full regression Phase 03–13 | Fresh per-phase DBs migrated to head; Redis; Docker sandbox; MinIO | **511 passed, 0 failed** |
| Demo compose stack rebuilt from `phase13` on its existing volumes | Docker Desktop (Windows host) | `migrate` applied both migrations; E2E **4 passed**. Live checks against MinIO: two identical snapshots → 200/200 and the worker ran the second (stdout `11`); valid checkpoint 200, RUN-snapshot checkpoint 422 `CHECKPOINT_SNAPSHOT_INVALID`; trace-state interval 60; practice list contains the new PUBLIC problem; admin settings show `idle_threshold_minutes` |

### 8.4 Known Limitations
- REQ-STU-004 (points) stays blocked by OQ-16. No frontend yet. OQ-26 (production judge isolation) and OQ-27 (`duration_minutes` meaning) remain open.
