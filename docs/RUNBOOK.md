# RUNBOOK — SPNC demo / development stack

> Phase 11 (docs/37). Docker Compose stack: PostgreSQL 16, Redis 7, MinIO, API, judge worker,
> reconciler, signal scheduler, exam scheduler, and the web client (`web`, Phase 20A, docs/46).
>
> **Not for production.** The judge worker mounts the host Docker socket (docs/37 D3), which
> gives it host-root-equivalent access. For production, run the judge on a dedicated host as
> described in §8 (OQ-26, resolved by docs/40 Q4).

## 1. Prerequisites
- Docker Engine / Docker Desktop with Compose v2.
- Sandbox images, pulled once (the worker starts them on demand):
  ```bash
  docker pull python:3.10-slim
  docker pull gcc:12
  ```

## 2. Configure
```bash
cp .env.example .env
```
Replace every `CHANGE_ME` value in `.env` with a long random string. `.env` is git-ignored; never commit it.

## 3. Start
```bash
docker compose up -d --build
docker compose ps
```
`migrate` runs `alembic upgrade head` once and exits; the other services start after it. The API listens on `http://127.0.0.1:8000` (Swagger UI at `/docs`). The MinIO console is at `http://127.0.0.1:9001`, using the `MINIO_ROOT_*` credentials.

## 4. Create the first admin (once)
```bash
docker compose exec api python -m app.cli create-admin --username admin --email admin@example.org
```
The password is `SPNC_BOOTSTRAP_ADMIN_PASSWORD` from `.env` (at least 12 characters). The admin must change it at first login (`POST /api/v1/auth/change-password`). A second run is refused: further accounts are created through `POST /api/v1/admin/users`.

## 5. Smoke test (cross-process judging, WebSocket)
From `apps/api`, with the stack running and a local Python environment that has `requirements.txt` installed:
```bash
SPNC_E2E_BASE_URL=http://127.0.0.1:8000 SPNC_E2E_ADMIN_USER=admin SPNC_E2E_ADMIN_PASSWORD='<bootstrap password>' SPNC_E2E_ADMIN_NEW_PASSWORD='<new admin password>' DATABASE_URL=postgresql://unused:unused@localhost/unused python -m pytest tests/e2e/test_compose_stack.py
```
It moves the admin to the new password the first time (and logs in with it on later runs). It creates a teacher and a student, a problem with two test cases, then checks that a Run and two Submissions are executed by the `worker` container (ACCEPTED 100, WRONG_ANSWER 50) and that `/api/v1/ws/teacher` authenticates.

## 6. Logs and troubleshooting
```bash
docker compose logs -f api worker
```
| Symptom | Cause / fix |
|---|---|
| Snapshot API returns 503 `STORAGE_UNAVAILABLE` | MinIO not reachable yet or down: `docker compose ps minio`, `docker compose logs minio`. Retry; nothing was written. |
| Run/Submission `FAILED_INTERNAL` "Snapshot content unavailable" | The worker could not read the blob (MinIO outage). Code is never judged as empty. |
| Run/Submission stays PENDING | Worker not running, or Redis lost the job: the reconciler re-queues after `JUDGE_STALE_RUN_TIMEOUT_SECONDS` / `JUDGE_STALE_SUBMISSION_TIMEOUT_SECONDS`. |
| Sandbox `Image not found` | Pull the images in §1. |
| Worker cannot reach Docker | `/var/run/docker.sock` must exist on the host (Docker Desktop: enabled by default). |

### Observability (docs/43)
- Probes: `curl http://127.0.0.1:8000/health` (process alive) and `curl http://127.0.0.1:8000/ready` (503 `NOT_READY` names the failed dependency: `database`, `redis` or `storage`; the reason is in the API log).
- Logs are JSON lines carrying `request_id` (also returned as the `X-Request-ID` header): `docker compose logs api | grep <request_id>`. `LOG_FORMAT=text` gives plain lines for local use.
- Metrics: every container serves Prometheus text on its internal port 9100 (not published), e.g. `docker compose exec reconciler python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:9100/metrics').read().decode())"`. A daemon is stuck when `spnc_daemon_last_success_timestamp_seconds` stops advancing.

## 7. Stop / reset
```bash
docker compose down        # keep data
docker compose down -v     # also delete PostgreSQL and MinIO volumes
```

## 8. Production judge host (docs/40 Q4)
The core stack (API, PostgreSQL, Redis, MinIO, reconciler, schedulers) runs **without** the `worker` service and without any Docker socket mount. Judge workers run on separate VMs:

1. **Database role** (once, as the database owner, after `alembic upgrade head`):
   ```bash
   psql "$DATABASE_URL" -f deploy/sql/judge_worker_role.sql
   psql "$DATABASE_URL" -c "ALTER ROLE spnc_judge PASSWORD '<secret>'"
   ```
   The role can read problems, test cases, snapshot metadata and exam max scores. It can update only judge results, the exam total and practice point awards (verified by `tests/infra/test_judge_isolation.py`).
2. **Read-only MinIO user** for the snapshot bucket (MinIO policy with `s3:GetObject` on `spnc-snapshots/*` only).
3. **Judge VM:** install Docker and gVisor, and register the runtime:
   ```bash
   sudo runsc install
   sudo systemctl restart docker
   docker run --rm --runtime=runsc python:3.10-slim python -c "print('gvisor ok')"
   docker pull python:3.10-slim
   docker pull gcc:12
   ```
4. **Firewall:** the judge VM may reach only the core PostgreSQL, Redis and MinIO ports.
5. **Start the worker** with `deploy/judge-host/docker-compose.yml`. Set `JUDGE_DATABASE_URL` (as `spnc_judge`), `JUDGE_REDIS_URL`, `JUDGE_S3_ENDPOINT`, `JUDGE_S3_ACCESS_KEY` and `JUDGE_S3_SECRET_KEY` in that host's `.env`; the file sets `JUDGE_CONTAINER_RUNTIME=runsc`.
   ```bash
   docker compose -f deploy/judge-host/docker-compose.yml up -d
   ```
6. **Check:** submit a practice solution and confirm the worker log shows the job and the submission ends `COMPLETED`. `docker inspect` on a running sandbox should show `"Runtime": "runsc"`.

Add more judge VMs to scale; each pulls jobs from the same Redis queue, and the CAS fencing (Phase 07/10A) keeps one result per job.

## 9. Backup and restore (docs/44)
A backup **set** is one directory `spnc-<UTC time>` holding `db.dump` (PostgreSQL, `pg_dump` custom format), `blobs/` (every snapshot blob the dump references) and `manifest.json` (alembic revision, row count per table, SHA-256 of the dump and of every blob). The key list and the dump come from one database snapshot, and every blob is hash-checked, so a set never restores rows that point at missing code.

### 9.1 Scheduled backups
The `backup` service runs one backup a day at `BACKUP_TIME_UTC` (default `19:00` UTC = 02:00 Asia/Ho_Chi_Minh) into `BACKUP_DIR` (default `./backups`, git-ignored) and keeps the newest `BACKUP_KEEP` sets (default 14). This meets RPO 24 h (OQ-20).
```bash
docker compose logs backup               # "Backup spnc-…: … rows in … tables, … blobs"
cat backups/last-backup.json             # status of the last run: ok / failed + error
```
A failed run leaves no set (only a `.partial` directory, removed by the next run) and writes `"status": "failed"` with the reason. A referenced blob missing from MinIO is a failure, never skipped.

### 9.2 Manual backup, list, check
```bash
docker compose run --rm backup backup
docker compose run --rm backup list
docker compose run --rm backup verify-set spnc-20261029T190000Z
docker compose run --rm backup verify-live      # every object_key of the live DB is readable and matches its hash
```

### 9.3 Off-host copy (required, docs/44 D7)
Sets live on the same disk as the volumes, so they do not survive the loss of the host. Copy each new set off the host, **encrypted**: sets contain personal data (trace events, audit log, password hashes). For example:
```bash
tar -C backups -cf - spnc-20261029T190000Z | age -r <recipient public key> > spnc-20261029T190000Z.tar.age
```
Keep the decryption key somewhere other than the backups. Data removed by the retention purge stays in backups until the set expires: effective retention is 180 days + `BACKUP_KEEP` days (OQ-21, docs/44 F8).

### 9.4 Restore (RTO 4 h)
Restore writes only into an **empty** database and bucket; it refuses anything else.
1. Stop the stack and keep the broken volumes aside if they may be needed for analysis; otherwise remove them:
   ```bash
   docker compose down -v
   ```
   On a new host: install Docker, check out the repository at the release that made the set, and create `.env` (§2).
2. Put the set (decrypted, unpacked) in `BACKUP_DIR`.
3. Start only storage, then restore:
   ```bash
   docker compose up -d postgres minio-init minio
   docker compose run --rm --no-deps backup restore spnc-20261029T190000Z
   ```
   It checks the set, uploads the blobs, then restores the database in one transaction, and finally compares the alembic revision, every table's row count and every `object_key` against the manifest. It prints `RESTORE OK`; on any mismatch it exits non-zero: do not start the stack.
4. Start everything; `migrate` is a no-op at the same revision (it upgrades if the code is newer):
   ```bash
   docker compose up -d
   docker compose run --rm --no-deps backup verify-live
   ```
5. Production judge host only (§8): roles are not part of the dump. Re-run `deploy/sql/judge_worker_role.sql` and set the `spnc_judge` password again.
6. Smoke test (§5). Users must log in again only if their refresh tokens are newer than the set.

Data written after the set was taken (at most 24 h) is lost; clients retry trace batches that were not acknowledged (docs/11 F01).

### 9.5 Restore drill
```bash
PYTHON=apps/api/venv/Scripts/python deploy/backup/drill.sh     # Linux/macOS: PYTHON=python3
```
On its own compose project (`spnc-drill`, API port 8018, console 9018; never the demo stack): starts a stack, seeds data (compose E2E + a drill teacher/class/submission), backs up, destroys every volume, restores into an empty stack, verifies, reads the seeded snapshot back through the teacher API, re-judges it, runs the compose E2E again and prints the restore time. CI runs it nightly and on demand (`backup-drill` job). Run it after any change to the schema or to the backup tool.

## 10. Retention purge (docs/45)
Raw trace (trace events, scratchpad revisions, checkpoint snapshots that no run, submission or final code uses, and their blobs) of sessions that ended more than `retention_days` ago is deleted; sessions, runs, submissions, scores, signals and audit logs stay. `retention_days` is the admin setting (`PATCH /api/v1/admin/settings`), 180 when unset, never below `RETENTION_MIN_DAYS` (30). Refresh tokens expired more than 7 days are removed too.
```bash
docker compose exec api python -m app.cli retention-purge             # dry run: counts only
docker compose exec api python -m app.cli retention-purge --apply     # delete (bounded: RETENTION_PURGE_MAX_BATCHES)
```
- Run a backup (§9.2) before the first `--apply`. Each applied batch writes an audit row `RETENTION_PURGE` with the session ids.
- Daily automatic purge: set `RETENTION_PURGE_ENABLED=true` for the `reconciler` (off by default); metrics `retention_purge_*` on its port 9100.
- Exam under dispute: `PUT /api/v1/admin/exams/{id}/retention-hold` with `{"hold": true, "reason": "…"}` keeps its sessions out of the purge until released.
- After a restore (§9.4) from a set older than a purge, the purged rows come back: run the purge again.

## 11. Web client (docs/46)
- **In the stack:** the `web` service serves the built SPA and proxies `/api/` (REST and the WebSocket) to `api`, so the browser uses one origin and no CORS is needed. Open `http://127.0.0.1:${WEB_PORT:-8080}`. `/docs`, `/health`, `/ready` and the metrics port are not reachable through it; use the API port for them.
- **Development:** from `apps/web`, `npm ci` once, then `npm run dev` (Vite on `http://127.0.0.1:5173`, proxying `/api` to `SPNC_API_TARGET`, default `http://127.0.0.1:8000`).
- **Checks:** `npm run lint`, `npm run typecheck`, `npm test` (Vitest, trace module), `npm run build`.
- **API client:** after any backend API change, regenerate and commit both files, or the CI `web` job fails:
  ```bash
  python scripts/web/dump_openapi.py
  ```
  then `npm run gen:api` in `apps/web`.
- **Browser E2E** (Playwright, with the stack running and the admin bootstrapped, §4): from `apps/web`, `npx playwright install chromium` once, then
  ```bash
  SPNC_WEB_URL=http://127.0.0.1:8080 SPNC_E2E_ADMIN_USER=admin SPNC_E2E_ADMIN_PASSWORD='<bootstrap password>' SPNC_E2E_ADMIN_NEW_PASSWORD='<new admin password>' npx playwright test
  ```
  It creates its own teacher, student and problem. One test waits about a minute for a checkpoint.
- **Browser storage:** unsent trace events and the editor draft of each open session are kept in the browser's IndexedDB (`spnc-trace`) until the server confirms them; logging out deletes them for that user. A trace-status badge above the editor shows unsent events.
- **Teacher screens (docs/47):** a TEACHER lands on `/teacher/classes` (create class, invite code, attention list, roster, student sessions, session replay with snapshot checks, signals, notes). Students join a class at `/classes` with the invite code. Live updates use the teacher WebSocket through `web`; a page shows "Trực tiếp" when connected.
