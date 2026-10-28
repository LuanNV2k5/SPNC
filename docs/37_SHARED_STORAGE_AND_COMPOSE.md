# 37 — SHARED SNAPSHOT STORAGE & COMPOSE STACK (PHASE 11) SPECIFICATION

> **Module:** Object storage adapter, first-admin bootstrap, Docker Compose stack (Phase 11)
> **Status:** APPROVED 2026-10-29 (all §6 recommendations; see PROJECT_PROVENANCE_LOG.md) — IMPLEMENTATION IN PROGRESS
> **Date:** 2026-10-29
> **Parent Baseline:** `phase10` @ `460dcdc` (Phase 10 implemented, lock pending)
> **Proposed Branch:** `phase11`
> **Target Lock Tag:** `phase-11-infra-locked`

---

## 1. Purpose

The architecture already fixes the target: snapshots in MinIO/S3, PostgreSQL holds metadata only, upload-first immutable blobs (docs/07, docs/10, ADR-007). The code still uses an in-memory dict per process (`app/services/storage.py`), so:
- a judge worker in its own process cannot read code uploaded by the API: every real Run/Submission ends `FAILED_INTERNAL` ("Snapshot content unavailable");
- snapshots vanish on restart;
- there is no way to stand the system up end to end for a demo.

Phase 11 makes the existing architecture real. **No requirement, endpoint contract or schema changes.**

---

## 2. Findings (2026-10-29)

| # | Finding | Location | Impact |
|---|---|---|---|
| F1 | Snapshot content lives in `StorageAdapter._memory_store` (per process). | `app/services/storage.py` | Cross-process judging impossible |
| F2 | No Dockerfile, no compose file, no documented way to run API + workers + schedulers together. | repo root | No demo / deployment path |
| F3 | No way to create the first ADMIN on an empty database (every user is created by an ADMIN). | — | Fresh stack cannot log in |
| F4 | `uvicorn` has no WebSocket library (`websockets`/`wsproto`), so `/api/v1/ws/teacher` cannot be served (docs/35 §10.4). | `requirements.txt` | Realtime unusable outside TestClient |
| F5 | The sandbox bind-mounts `JUDGE_TEMP_DIR` into sibling containers. When the worker itself runs in a container and talks to the host daemon, the bind source is resolved **on the host**, so the path must be identical inside and outside the worker. | `app/services/judge/sandbox.py` | Worker-in-container needs a same-path volume |
| F6 | Object keys are `snapshots/{session}/0_{sha256[:8]}.txt` (sequence always 0) with a UNIQUE constraint: two snapshots with identical content in one session collide on insert. | `storage.py`, `code_snapshots.object_key` | Pre-existing; noted, not changed here (key format is persisted data) |

---

## 3. Scope

### 3.1 Storage adapter
- `StorageAdapter` keeps its three methods (`upload_code_snapshot`, `download_code_snapshot`, `exists_code_snapshot`); callers do not change.
- Two backends chosen by `STORAGE_BACKEND`: `memory` (default; tests and local dev unchanged) and `s3` (MinIO/S3 via the official `minio` client). Settings: `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` (default `spnc-snapshots`), `S3_SECURE` (default false), `S3_REGION`.
- Upload-first (ADR-007): the blob is written before the metadata row. Object keys keep the current format (F6), so existing rows stay valid.
- Immutability: an upload never overwrites an existing object with different content; uploading identical content again is a no-op (same key = same hash).
- Failures: upload error → snapshot API returns 503 `STORAGE_UNAVAILABLE` and no metadata row is written. Download/exists errors in the worker → the existing `FAILED_INTERNAL` path ("Snapshot content unavailable"), never empty code. `finalize_session` already tolerates missing content (`final_loc = null`).
- The bucket is created on startup if missing (idempotent).

### 3.2 First-admin bootstrap
`python -m app.cli create-admin --username U --email E` reads the password from env `SPNC_BOOTSTRAP_ADMIN_PASSWORD` (never a CLI argument, never logged), creates an ACTIVE ADMIN with `force_password_change = true`, writes AuditLog `ADMIN_BOOTSTRAPPED` (actor null). It refuses (exit 1) when any ADMIN already exists, so it cannot be used to add admins later.

### 3.3 Compose stack (`docker-compose.yml` at repo root, `apps/api/Dockerfile`)
| Service | Command | Notes |
|---|---|---|
| `postgres` | postgres:16-alpine | named volume |
| `redis` | redis:7-alpine | |
| `minio` | minio/minio | named volume; console port local only |
| `migrate` | `alembic upgrade head` | one-shot; app services wait for it |
| `api` | `uvicorn app.main:app` | port 8000 |
| `worker` | `python -m app.worker` | judge worker; Docker access per D3 |
| `reconciler` | `python -m app.reconciler` | |
| `signal-scheduler` | `python -m app.signal_scheduler` | |
| `exam-scheduler` | `python -m app.exam_scheduler` | |

All secrets come from a `.env` file (`.env.example` committed, `.env` git-ignored). Sandbox images (`python:3.10-slim`, `gcc:12`) are pulled by a documented one-time step. A short `docs/RUNBOOK.md` covers start, bootstrap admin, smoke test and stop.

### 3.4 Out of scope
Frontend/NGINX/TLS (docs/10 shows them; no frontend exists); orphan-blob cleanup worker (ADR-007 risk; separate phase); the F6 key format; production hardening of the judge zone (see D3); horizontal scaling.

---

## 4. Invariants
1. Code is never fabricated: missing or unreadable content is `FAILED_INTERNAL` / `final_loc = null`, never empty source (DTI-06).
2. No DB metadata row without a stored blob (upload-first).
3. Stored blobs are never modified.
4. Student code still never runs in the API process; sandbox limits unchanged (Rules 18, 19).
5. Tests keep running without MinIO (memory backend), except the dedicated MinIO tests.

---

## 5. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-11-01 | S3 backend against a real MinIO: upload → exists → download round trip; identical re-upload is a no-op; different content under an existing key is refused; missing key → `exists=false`. |
| AC-11-02 | MinIO unavailable: snapshot API → 503 `STORAGE_UNAVAILABLE`, no metadata row; worker → `FAILED_INTERNAL`. |
| AC-11-03 | **Cross-process judging:** with the compose stack up, a student submission created through the API is judged by the separate worker container and ends `COMPLETED` with the expected verdict; a Run does the same. |
| AC-11-04 | Bootstrap creates exactly one ADMIN with forced password change and an AuditLog row; a second run exits 1. |
| AC-11-05 | `/api/v1/ws/teacher` accepts a WebSocket connection when served by uvicorn in the stack. |
| AC-11-06 | Full Phase 03–10 regression passes on fresh databases (memory backend). |

---

## 6. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | S3 client library | (a) `minio` (small, S3-compatible); (b) `boto3` (heavy, AWS-first) | **(a)** |
| **D2** | Backend selection | (a) `STORAGE_BACKEND=memory|s3`, default memory; (b) S3 only, tests need MinIO | **(a)**. Keeps the 469 existing tests independent of MinIO. |
| **D3** | How the containerised judge worker reaches Docker | (a) mount the host Docker socket into the `worker` container, **demo/dev only** (gives that container host-root-equivalent access; documented as not production-grade); (b) run the worker on the host, outside compose; (c) Docker-in-Docker sidecar (privileged) | **(a)** for the demo stack, with a warning in the compose file and RUNBOOK. Production isolation of the judge zone (docs/10 §2) is tracked as OQ-26. |
| **D4** | First admin | (a) CLI bootstrap per §3.2; (b) migration-seeded default admin | **(a)**. No default credentials in code or migrations. |
| **D5** | WebSocket dependency | (a) add `websockets` to requirements; (b) `wsproto` | **(a)** |
| **D6** | Upload failure status | (a) 503 `STORAGE_UNAVAILABLE`; (b) 500 | **(a)**. Transient and retryable for the client. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before implementation.

---

## 7. Verification Record

*To be completed at Phase 11 closure.*
