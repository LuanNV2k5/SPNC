# RUNBOOK — SPNC demo / development stack

> Phase 11 (docs/37). Docker Compose stack: PostgreSQL 16, Redis 7, MinIO, API, judge worker,
> reconciler, signal scheduler, exam scheduler. Backend only (no frontend yet).
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
