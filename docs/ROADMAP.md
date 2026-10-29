# ROADMAP — next phases and go-live gate

> **Status:** APPROVED 2026-10-29 by the Project Owner (see PROJECT_PROVENANCE_LOG.md, "Roadmap after Phase 19")
> **Baseline:** `phase-19-retention-locked`

This file records **ordering decisions and gates** between phases. It is not a specification: every phase listed here still goes spec → Project Owner approval → implementation with tests → regression → lock (PROJECT_RULES).

---

## 1. Done (risk-ordered plan)
| Step | Phase | Tag |
|---|---|---|
| 1 CI and branch protection | 16 (docs/42) | `phase-16-ci-locked` |
| 2 Observability | 17 (docs/43) | `phase-17-observability-locked` |
| 2 Backup and restore | 18 (docs/44) | `phase-18-backup-locked` |
| 3 Retention purge | 19 (docs/45) | `phase-19-retention-locked` |

## 2. Next: frontend phase
The frontend is the next phase. Its specification **must** contain a decision on how the browser reaches the API, because the backend has no CORS configuration today (no `CORSMiddleware` in `app/main.py`, no reverse proxy in `docker-compose.yml`). A browser page served from another origin (for example a dev server on `localhost:5173` calling `localhost:8000`) is blocked.

The frontend spec presents at least these options, each with a recommendation:

| Option | What | Notes for the spec |
|---|---|---|
| (a) CORS in the API | `CORSMiddleware` with an explicit origin list from configuration (e.g. `CORS_ALLOW_ORIGINS`), never `*` in production | Auth uses `Authorization: Bearer` headers, not cookies, so credentials mode is not needed. Allowed methods and headers must include `Authorization`, `Content-Type` and `X-Request-ID`. |
| (b) Same origin via reverse proxy | One host serves the frontend build, `/api/v1/...` including the WebSocket (`/api/v1/ws/teacher`), e.g. NGINX as in docs/10 | No CORS needed. TLS terminates at the proxy. WebSocket upgrade headers are forwarded. `/metrics` port 9100 stays unpublished (docs/43 §4.3). |
| (c) Both | (b) in production, (a) only for local development | |

Also in that spec: WebSocket connections are not covered by CORS, so the spec states whether the WebSocket endpoint checks `Origin`.

## 3. Go-live gate G1 (hard)
**Before the first real user** (any real student or teacher account, or real student data on a deployment), both items below are done, each through its own locked phase. Until then the system runs only with test or demo data.

| Item | Done means |
|---|---|
| **G1.1 Off-host backup copy** | Every backup set (docs/44) is copied off the host **encrypted**, automatically or by a scheduled documented job. Its success or failure is visible. A restore **from the off-host copy** has been performed once and recorded (RUNBOOK §9.3–9.5). The decryption key is stored apart from the copies. |
| **G1.2 Minimal alerting** | Someone is notified, not just a metric exposed, when: the last backup failed or is older than 26 h (`backups/last-backup.json`); a daemon's `spnc_daemon_last_success_timestamp_seconds` is stale; `/ready` returns 503; `judge_queue_depth` stays high; disk usage passes 70 % / 80 % (docs/11). |

G1 is checked when the go-live decision is taken: the lock entries of the two phases are cited in PROJECT_PROVENANCE_LOG next to that decision.

## 4. Deferred (no fixed order)
Load test (after the frontend exists, so the client's real trace and checkpoint rhythm is measured); compose `healthcheck:` for `api` using `/ready`; the metrics deferred in docs/43 §7.4; dashboards; enabling the daily retention purge (`RETENTION_PURGE_ENABLED`, after a backup, RUNBOOK §10; nothing is older than 180 days yet); trace partitioning (docs/17 §4); trace export to cold storage and audit-log expiry (docs/45 §3.9).
