# 44 — BACKUP & RESTORE (PHASE 18 / STEP 3) SPECIFICATION

> **Module:** Consistent backup of PostgreSQL + snapshot blobs, scripted restore, restore drill
> **Status:** APPROVED 2026-10-29 (all §7 recommendations; see PROJECT_PROVENANCE_LOG.md) — LOCKED 2026-10-29 (`phase-18-backup-locked`, on the merge commit of the lock PR)
> **Date:** 2026-10-29
> **Parent Baseline:** `phase-16-ci-locked` (`0ad5a9b`, = `main`)
> **Proposed Branch:** `phase18`
> **Target Lock Tag:** `phase-18-backup-locked`

---

## 1. Purpose

OQ-20 fixed **RPO ≤ 24 h** and **RTO ≤ 4 h** and requires backing up "PostgreSQL + persistent snapshot/object metadata" (NFR-REL-004, NFR-REL-007). Nothing implements it yet. The next step after this phase is the 180-day trace retention purge (OQ-21, NFR-DATA-008), which deletes data for real; it must not start before a backup has been **restored and verified** at least once.

This phase delivers:
- a backup that captures PostgreSQL and the MinIO snapshot blobs **as one consistent set**;
- a scripted restore into an empty stack;
- a **restore drill** that proves the set is complete and measures the time to recover.

**No application behaviour changes in this phase.**

---

## 2. Findings (2026-10-29)

| # | Finding | Evidence | Impact |
|---|---|---|---|
| F1 | No backup exists. docs/10 §1 and docs/11 F01 say "restore from backup (RPO 24h, RTO 4h)", but there is no tool, schedule, location or procedure. | `docker-compose.yml`, `docs/RUNBOOK.md` (no backup section) | A broken `pgdata` volume loses everything |
| F2 | Data lives in two stores. PostgreSQL holds all metadata, users, audit log, trace events; MinIO holds code snapshot content under `code_snapshots.object_key` (`snapshots/<session_id>/<sha256>.txt`). | `app/services/storage.py`, `app/models/trace.py:60` | A DB backup alone restores rows whose code cannot be read: Run/Submission become `FAILED_INTERNAL` "Snapshot content unavailable" |
| F3 | Blobs are **immutable and content-addressed**, and writes are **upload-first** (blob before row). | `storage.py` docstring, `StorageConflict` | Any blob a committed row references existed before the row was committed. Copying blobs **after** the DB snapshot therefore always finds every referenced blob (unless something deleted it in between, F4) |
| F4 | The only blob deletion today is the orphan sweep: it deletes blobs **not** referenced by any row and older than 24 h. The future retention purge (OQ-21) will delete rows and then their blobs. | `app/services/snapshot_cleanup.py`, `SNAPSHOT_ORPHAN_GRACE_HOURS` | Between the DB snapshot and the blob copy, a purge could remove a blob the dump still references. The backup must check this, not assume it |
| F5 | A restored database with blobs missing would let the orphan sweep and the API run on an inconsistent state without any error until a student's code is read. | — | Restore must verify **every** `object_key` before the stack is opened |
| F6 | Compose hard-codes the MinIO console port `9001`, so a second stack (drill, or restore next to the running one) cannot start on the same host. | `docker-compose.yml` `minio.ports` | Drill needs a parametrised port |
| F7 | No `pg_dump`/`psql` on the Windows host; Docker is available. The CI runner (`ubuntu-24.04`) has Docker and Compose. | `which pg_dump` | The tooling must run in a container, the same on the host, in the stack and in CI |
| F8 | Backups keep personal data (trace events, audit log). Once the retention purge exists, deleted data survives in older backups until those backups expire. | OQ-21 | Backup retention adds to the effective retention period and must be stated (D5) |

---

## 3. Scope

### 3.1 Backup tool `deploy/backup/`
One small Python program (`spnc_backup.py`) in its own image (`deploy/backup/Dockerfile`, from `postgres:16-alpine` so `pg_dump`/`pg_restore` match the server major version, plus Python with `psycopg2` and `minio`). Subcommands:

| Command | Does |
|---|---|
| `backup` | Creates one backup set (§3.2), verifies it, then prunes old sets (D5). Non-zero exit on any failure; an incomplete set is never left with a final name. |
| `verify-set <set>` | Re-checks a set offline: manifest checksums, every blob present with matching SHA-256. |
| `restore <set>` | Into an **empty** database and bucket only (refuses otherwise): blobs first, then `pg_restore`, then post-restore verification (§3.3). |
| `verify-live` | Checks a running database + bucket: every `code_snapshots.object_key` resolvable and its content hash matching the key. Usable any time, not only after a restore. |
| `schedule` | Long-running loop for the compose service: runs `backup` once a day at `BACKUP_TIME_UTC` (D2). |

### 3.2 Backup set (consistency, D3)
1. Open a `REPEATABLE READ` transaction and **export its snapshot** (`pg_export_snapshot()`).
2. In that snapshot: read every `code_snapshots.object_key` and the row count of every table.
3. `pg_dump --format=custom --snapshot=<id>`: the dump contains exactly the state read in step 2.
4. Copy **only the referenced blobs** from MinIO into the set, checking each blob's SHA-256 against the hash in its key. A referenced blob that is missing fails the backup (F4) — it is reported, never silently skipped.
5. Write `manifest.json`: time, alembic revision, PostgreSQL version, table row counts, object count, SHA-256 of `db.dump` and of every blob.
6. Rename the staging directory to its final name `spnc-<UTC timestamp>` (atomic; a crash leaves only a `.partial` directory, which the next run removes).

Orphan blobs (no row references them) are not backed up: they are garbage by definition (docs/39 D2).

### 3.3 Restore and verification
Restore target must be empty (fresh volumes). Order: blobs uploaded first, then `pg_restore --exit-on-error --no-owner`, so the upload-first invariant holds during the restore too. Then verification, all must pass:
- `alembic_version` equals the manifest revision;
- every table's row count equals the manifest;
- every `object_key` in the restored database exists in the bucket and its content hash matches.

Only then is the rest of the stack (`migrate`, API, workers, schedulers) started. `migrate` is a no-op on a restored database at the same revision, and upgrades it if the code is newer.

### 3.4 Compose and runbook
- `backup` service in `docker-compose.yml` (D4), writing to `${BACKUP_DIR:-./backups}` on the host (git-ignored).
- `MINIO_CONSOLE_PORT` (default `9001`) replaces the hard-coded console port (F6). Defaults keep the existing stack unchanged.
- `docs/RUNBOOK.md` §9 "Backup and restore": manual backup, listing sets, off-host copy, full restore procedure step by step, drill.

### 3.5 Restore drill `deploy/backup/drill.sh` (D6)
Runs on its own compose project (default `spnc-drill`, own ports and volumes; never the demo stack):
1. start a stack, bootstrap the admin, run the compose E2E (creates users, problem, snapshots, Run, Submissions, trace);
2. `backup`;
3. `down -v` (destroy all data);
4. start empty `postgres` + `minio`, `restore` the set (verification §3.3);
5. start the full stack; run `verify-live`; the drill's teacher reads a snapshot created before the backup through the API (`tests/e2e/test_backup_drill.py`), the pre-backup submission keeps its verdict, the worker judges a pre-backup snapshot; run the compose E2E again;
6. print the elapsed restore time (step 4 start → step 5 E2E green) and tear down.

### 3.6 Tests
`apps/api/tests/infra/test_backup.py` (in the `phase10plus` group): drives `spnc_backup.py` functions against the test PostgreSQL and MinIO — set creation, manifest, missing referenced blob fails the backup, corrupted blob or dump fails `verify-set`, restore refuses a non-empty target, restore round trip (counts, keys), pruning keeps the newest N, `.partial` cleanup. `pg_dump`/`pg_restore` run in the `postgres:16-alpine` image through Docker when the host has no client (F7), so the same test runs on Windows and in CI.

---

## 4. Invariants
1. **No dangling keys.** A restored database never references a blob that the restored bucket does not hold with the right content; restore fails loudly instead of opening the stack.
2. A backup set is either complete and verified, or it does not exist under a final name.
3. Backup and restore never modify the source stack (read-only DB transaction, read-only blob access).
4. Restore writes only into an empty target.
5. Drills and tests never touch the demo stack (project `phase11`) or its volumes.
6. Credentials come from `.env`; the backup set contains no `.env` and no secrets other than what the database itself holds (password hashes).

---

## 5. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-18-01 | `backup` on a stack with data produces a set whose manifest lists every referenced `object_key`, with matching SHA-256 values. |
| AC-18-02 | A referenced blob missing from MinIO makes `backup` fail and leaves no final set. |
| AC-18-03 | `verify-set` detects a corrupted `db.dump` and a corrupted blob. |
| AC-18-04 | `restore` refuses a non-empty target; on an empty target, row counts, alembic revision and every key match the manifest. |
| AC-18-05 | Restore drill on this machine passes end to end (§3.5); the measured restore time is recorded and is far below RTO 4 h. |
| AC-18-06 | The scheduled `backup` service produces a set at the configured time (checked with a time set a few minutes ahead) and prunes per D5. |
| AC-18-07 | New tests in a regression group; full `regression.sh all` green locally on a fresh PostgreSQL; `ci` green on the PR. |
| AC-18-08 | The drill job runs green on GitHub Actions (D6). |
| AC-18-09 | The existing stack starts unchanged with default `.env` values (`MINIO_CONSOLE_PORT` defaults to 9001). |

---

## 6. Out of Scope
- The retention purge itself (next phase).
- Point-in-time recovery (WAL archiving); see D1 for the upgrade path.
- Pushing backups to a cloud provider; the runbook gives the off-host copy step (D7).
- Redis: it holds only transient queue/pub-sub state; the reconciler rebuilds lost jobs from PostgreSQL (docs/11 F02).

---

## 7. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | PostgreSQL backup method | (a) logical `pg_dump --format=custom` once a day; (b) physical base backup + continuous WAL archiving (PITR, RPO minutes); (c) volume/filesystem snapshot | **(a)**. Meets RPO 24 h, restorable on any PostgreSQL 16 host, simple to verify. (b) is the upgrade path if RPO tightens; (c) is not consistent with the blob store and depends on the host. |
| **D2** | Schedule | (a) daily at 19:00 UTC (02:00 Asia/Ho_Chi_Minh, low traffic), configurable `BACKUP_TIME_UTC`, plus manual runs any time; (b) every 12 h; (c) manual only | **(a)**. Worst-case data loss 24 h = RPO. |
| **D3** | DB/blob consistency | (a) exported snapshot: key list and dump from the same DB snapshot, then copy only referenced blobs, verify each hash; a missing blob fails the backup; (b) dump DB, then mirror the whole bucket without checks; (c) stop the API during backup | **(a)**. Exact and needs no downtime; relies on F3 (immutable, upload-first). (b) can silently miss a blob (F4) and copies orphans; (c) costs availability for no gain. |
| **D4** | Who runs the schedule | (a) a `backup` service in `docker-compose.yml` (same image tooling everywhere, starts with the stack); (b) host cron / Windows Task Scheduler calling the script | **(a)**. Portable and visible in `docker compose ps`; (b) differs per host OS. The script can still be run by hand or by host cron. |
| **D5** | Where sets are stored, how long kept | (a) host directory `${BACKUP_DIR:-./backups}`, one self-contained directory per set (dump + blobs + manifest), keep the newest **14** (`BACKUP_KEEP`); effective retention of deleted data = 180 days + 14 days, documented; (b) shared deduplicated blob store across sets with reference-counted pruning; (c) keep 30 sets | **(a)**. A self-contained set can be copied off-host and restored on its own. Snapshot text blobs are small, so duplication is cheap at V1 scale; (b) is the upgrade if size grows. |
| **D6** | Restore drill | (a) `deploy/backup/drill.sh` run once now on this machine (recorded here) and as a CI job on the nightly schedule and on demand; (b) only now, manually; (c) also on every PR | **(a)**. Proves restorability continuously without slowing PRs (builds the stack twice, like `compose-e2e`). Additive job in `ci.yml`, not a required check. |
| **D7** | Encryption and off-host copy | (a) no tool-level encryption in V1: sets inherit the host's disk protection (same as the live volumes), directory created `0700`; the runbook requires an encrypted off-host copy (e.g. `age`/`gpg` or an encrypted remote) operated by the deployment; (b) built-in symmetric encryption (`age` with a passphrase from `.env`) of every set; (c) none, no guidance | **(a)** for the demo/V1 stack. (b) adds key management that must itself be backed up; worth doing when a real deployment copies sets to third-party storage. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md`.

---

## 8. Verification Record

### 8.1 Changes (2026-10-29)
| Commit | Content |
|---|---|
| `1c70172` | Spec approval (PROJECT_PROVENANCE_LOG) |
| `c49b4d6` | `deploy/backup/` (`spnc_backup.py`, `Dockerfile`, `drill.sh`), `backup` service and `MINIO_CONSOLE_PORT` in `docker-compose.yml`, `.env.example`, `tests/infra/test_backup.py` (group `phase10plus`), `tests/e2e/test_backup_drill.py`, CI job `backup-drill`, RUNBOOK §9 |
| `d1cc8b8` | Test fix found by CI (§8.2) and a test that an existing set is never overwritten |
| `70e3e6b` | Regression runner and seven test files honour `PG_BASE` (§8.2) |

Implementation notes:
- The restore uses `pg_restore --no-owner --no-privileges`: roles are cluster objects and not in the dump. RUNBOOK §9.4 step 5 re-creates the production judge role.
- Restore verification compares blobs with `code_snapshots.source_hash` rather than the key name, so Phase 06 keys (`<seq>_<hash>.txt`, docs/39) are checked too.
- Sets are named to the second; a second backup in the same second is refused, never overwritten.
- `backups/last-backup.json` records the last scheduled run (`ok`/`failed` + reason) for monitoring.
- In tests, `pg_dump`/`pg_restore` run in `postgres:16-alpine` through Docker (`host.docker.internal`), the same on Windows and on the CI runner.

### 8.2 Defects Found
- **Same-second backups (test only).** On the faster CI runner, `test_scheduled_backup_writes_status` ran two backups in the same second into one directory; the second was correctly refused ("already exists"), so the test expected the wrong error. The test now uses separate directories, and a new test pins the refusal.
- **Local regression did not honour `PG_BASE` (since Phase 16).** Seven test files hard-coded `localhost:5432` (`test_auth`, `test_admin`, `test_academic`, `test_trace`, `test_run`, `test_fencing`, `test_queue`), and eight more read `PHASE08E/09/10_DATABASE_URL`, whose default is also `localhost:5432`. CI was unaffected (its database is on 5432), but a local run with another `PG_BASE` silently used the shared 5432 container for those files. During this phase that caused a lock wait between this regression and the parallel Phase 17 regression on the same database, and `test_queue.py::test_Q06` failed because the test wrote to 5432 while `reconcile()` read `PG_BASE`. Fixed: the files read `TEST_DATABASE_URL` (default unchanged), and `regression.sh` also sets the three `PHASE*` variables. Checked with the shared container's per-database transaction counters during the full run (§8.3).

### 8.3 Verification
| Check | Environment | Result |
|---|---|---|
| AC-18-01…04 `tests/infra/test_backup.py` | Disposable PostgreSQL 16 (port 55433), MinIO test container, `pg_dump`/`pg_restore` 16 in Docker | **19 passed**: complete set and manifest, orphan excluded; missing and tampered blob fail the backup with no set left; one snapshot for keys and dump (a row committed during the backup is in neither); corrupted dump / blob / missing blob detected; restore round trip; non-empty database or bucket refused; corrupted set refused before anything is written; `verify-live`; pruning and `.partial` cleanup; status file; schedule time; unsafe keys |
| AC-18-05 restore drill | This machine, project `spnc-drill` (API 8018, console 9018), Docker Desktop | **PASSED**: set `spnc-20261029T131739Z` (59 rows, 25 tables, 5 blobs, revision `b2d8f5a9c314`); all volumes destroyed; restore + verification + full stack + `verify-live` + teacher reads the pre-backup snapshot via `GET …/snapshots/{id}` + pre-backup submission still `ACCEPTED 100` + a pre-backup snapshot judged by the worker + compose E2E 4 passed. **Restore time 22 s** (RTO 4 h = 14 400 s). Two earlier drill runs failed in the drill's own steps (a practice session ends on submission; Git Bash path conversion), both fixed before this run |
| AC-18-06 schedule | Project `spnc-p18-sched`, `BACKUP_TIME_UTC` = 3 min ahead, `BACKUP_KEEP=2`, two old sets present | set `spnc-20261029T131600Z` created at 13:16:00 UTC, oldest set pruned, `last-backup.json` `ok`, next run scheduled +24 h |
| AC-18-07 full regression | This machine, `regression.sh all`, `PG_BASE` on port 55433 | **557 passed, 0 failed** (45 files; Phase 16 baseline 538 + 19 new). The shared 5432 container's per-database transaction counters rose only by its idle background rate (2–4 per 100 s per database, measured afterwards; about 30 over the run), so no test used it |
| AC-18-07 CI | GitHub Actions run 40881419054 (`d1cc8b8`) | all 6 groups green, `ci` green |
| After merging `main` (Phase 17) into `phase18` (`465ed4b`) | This machine | restore drill **passed, 20 s**; `regression.sh all` **580 passed, 0 failed** (46 files = 557 + Phase 17's 23) |
| PR [#5](https://github.com/LuanNV2k5/SPNC/pull/5) CI | runs 40891127487, 40891190579 (`465ed4b`) | all 6 groups green, `ci` green |
| AC-18-08 drill on GitHub | run 40880784168 (`workflow_dispatch`, `c49b4d6`) | `backup drill` **success**, `compose E2E` success (the `phase10plus` failure in that run is the §8.2 test fix) |
| AC-18-09 defaults | `docker compose config` with the Phase 16 `.env.example` (no new variables) | API 8000, console 9001 unchanged; backup defaults `./backups`, `19:00`, 14 |
| Demo stack untouched | `docker ps` | project `phase11` containers and volumes unchanged throughout |
