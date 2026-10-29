# 43 — OBSERVABILITY (PHASE 17 / STEP 2) SPECIFICATION

> **Module:** metrics, health/readiness probes, structured logs, log hygiene
> **Status:** DRAFT — awaiting Project Owner approval of §6
> **Date:** 2026-10-29
> **Parent Baseline:** `phase-16-ci-locked` (`0ad5a9b`, = `main`)
> **Proposed Branch:** `phase17`
> **Target Lock Tag:** `phase-17-observability-locked`

---

## 1. Purpose

Step 2 of the risk-ordered plan. Before retention purges, load tests and a production deployment, an operator must be able to answer three questions without reading the database by hand:
- **Is it up?** Each process can be probed; the API can say whether its dependencies (PostgreSQL, Redis, snapshot storage) are reachable.
- **Is it healthy?** The integrity metrics already named in `docs/07_SYSTEM_ARCHITECTURE.md` §4 (judge fencing, stale jobs, snapshot blobs, trace conflicts, WebSocket auth) exist and can be scraped.
- **What happened to request X?** Every log line is one JSON object carrying `request_id` (and `session_id`, `run_id`, … where applicable), so one request can be followed across the log.

Metrics and logs stay **operational evidence**; PostgreSQL remains the academic source of truth (docs/07 §4). **No business behaviour changes in this phase.**

---

## 2. Findings (2026-10-29)

| # | Finding | Evidence | Impact |
|---|---|---|---|
| F1 | No metric is implemented. docs/07 §4.1–4.5 names about 30 (e.g. `snapshot_upload_failure_total`, `snapshot_orphan_cleanup_failure_total`, `snapshot_blob_missing_total`, `run_fencing_rejection_total`, `judge_queue_depth`); none exists in code, and no metrics library is in `requirements.txt`. | `grep -rn metric apps/api/app` → nothing | Alerts A1–A10 (docs/07 §4.6) cannot be built |
| F2 | No health or readiness endpoint. `main.py` mounts only `/api/v1/...` routers. Compose has healthchecks only for `postgres` and `redis`; `api`, `worker`, `reconciler` and both schedulers have none. | `app/main.py`, `docker-compose.yml` | A dead API or a lost database connection is invisible until users report it |
| F3 | Logs are unstructured text from `logging.basicConfig(level=INFO)`, configured separately in each daemon (`worker.py`, `reconciler.py`, `signal_scheduler.py`, `exam_scheduler.py`); the API configures nothing. `request_id` exists (`main.py` middleware, error bodies) but never appears in any log line. | the four daemons, `app/main.py` | A failed request cannot be traced in the logs |
| F4 | `services/queue.py` reports enqueue failures with `print()`, bypassing logging. | `queue.py:21,31` | Lost on log shipping; no level, no context |
| F5 | The request-id middleware accepts any client-sent `X-Request-ID` unchanged (any length, any characters) and echoes it into headers and error bodies. | `main.py` `add_request_id` | Log injection / forged correlation ids once ids are logged |
| F6 | An unhandled exception in a request returns Starlette's plain-text `Internal Server Error`, without `error_code` or `request_id` (PROJECT_RULES #29), and is not logged with the request id. | only four exception handlers in `main.py` | 500s cannot be correlated |
| F7 | Uvicorn's default access log prints the full URL including the query string. No endpoint carries a credential in the URL today (WebSocket auth is sent as the first message, `ws.py` header comment), but nothing prevents it later. | Dockerfile `CMD uvicorn …` | Future token-in-URL would land in logs |
| F8 | The background daemons are separate processes (one container each in compose); in-process metric registries are not shared with the API. | compose services `worker`, `reconciler`, `signal-scheduler`, `exam-scheduler` | Daemon metrics need their own exposure path (D3) |
| F9 | Log content is safe today by inspection: no log line contains a password, token, request body, source code or trace payload. `worker.py` stores `str(e)` of a sandbox failure in `testcase_results.stderr` (database, not log) and logs it only via `logger.exception`. The only guard is review discipline. | grep of every `logger.` call | PROJECT_RULES #25 has no automated check |

---

## 3. Scope

### 3.1 Metrics (D1, D2)
- New module `app/core/metrics.py`: one place that defines every metric (names from docs/07 §4 where they exist), so services import a metric object instead of creating ad-hoc ones.
- Instrumentation points (counters are incremented in services/repositories, not routers — PROJECT_RULES #7):

| Area | Metric (type) | Incremented where |
|---|---|---|
| HTTP | `http_requests_total{method,route,status}` (counter), `http_request_duration_seconds{method,route}` (histogram) | middleware; `route` = route **template** (`/api/v1/my/coding-sessions/{session_id}/runs`), never the raw path, so ids never become labels; unmatched paths → `route="unmatched"` |
| Trace | `trace_ingest_batch_total{outcome}` with outcome `accepted`/`duplicate`/`rejected`; `trace_conflicting_duplicate_total`; `trace_batch_retry_total` (batch whose events all already existed); `trace_ingest_latency_seconds` (histogram) | `services/trace.py` |
| Judge | `run_claim_conflict_total{kind}` (CAS lost / not PENDING), `run_fencing_rejection_total{kind}` (`write_result` matched 0 rows), `run_reenqueue_total{kind}` (reconciler recovered a stale job), `judge_execution_duration_seconds{kind}`, `judge_worker_failure_total{kind}` (FAILED_INTERNAL), `judge_queue_depth` (gauge, `LLEN judge_queue`), `judge_enqueue_failure_total{kind}` | `repositories/run.py`, `services/submission.py`, `worker.py`, `reconciler.py`, `services/queue.py`; `kind` = `run`/`submission` |
| Snapshot | `snapshot_upload_failure_total`, `snapshot_blob_missing_total{reader}`, `snapshot_orphan_detected_total`, `snapshot_orphan_cleanup_total`, `snapshot_orphan_cleanup_failure_total` | `services/storage.py`, `services/snapshot_cleanup.py`, the four `exists_code_snapshot` callers |
| Realtime | `websocket_active_connections` (gauge), `websocket_auth_rejection_total{reason}` | `api/endpoints/ws.py` → small helper in `realtime/` |
| Daemons | `spnc_daemon_cycles_total{daemon,outcome}`, `spnc_daemon_last_success_timestamp_seconds{daemon}` (gauge) | each daemon loop |

- **Deferred** (named in docs/07 but need new detection logic, not just a counter): `trace_sequence_gap_total` (gap analysis), `run_pending_stale_total` / `run_running_stale_total` as separate series (the reconciler counts recoveries, not the two states), `run_duplicate_delivery_total` (indistinguishable from a claim conflict without delivery ids), `websocket_revocation_disconnect_total`, `websocket_reconnect_total`, PostgreSQL pool utilisation. They are listed in §7 as follow-ups.

### 3.2 Metric exposure (D3, D5)
Every process — the API and each of the four daemons — serves Prometheus text format on its own **internal** port `METRICS_PORT` (default 9100; `0` disables) with `prometheus_client.start_http_server`. The public API port (8000) does not serve `/metrics`. Compose publishes only `127.0.0.1:8000` for the API and no port at all for daemons, so 9100 is reachable only on the compose network; **no compose change is needed** (Phase 18 owns compose).
- Daemons start the listener in their `__main__` block only (importing a daemon module in tests starts nothing).
- The API gets a small launcher `python -m app.serve` (new Docker `CMD`): starts the metrics listener, configures logging, then runs uvicorn with its access log disabled (our middleware logs instead, §3.4). Tests import `app.main:app` as before and never open a port.
- The API container runs one uvicorn process today; the in-process registry is therefore complete. Running several uvicorn workers per container would need `prometheus_client` multiprocess mode — recorded as an invariant (§4.5), not built now.
- A Prometheus server, dashboards and alert rules are **out of scope** (production-infrastructure step); this phase makes the data available.

### 3.3 Health and readiness (D4)
| Endpoint | Meaning | Checks | Response |
|---|---|---|---|
| `GET /health` | liveness: the process answers | none | `200 {"status": "ok"}` |
| `GET /ready` | readiness: the API can serve requests | PostgreSQL `SELECT 1`; Redis `PING`; snapshot storage reachable (S3: bucket exists; memory backend: always ok). Each with a short timeout (≤ 2 s) | all ok → `200 {"status": "ready", "checks": {"database": "ok", "redis": "ok", "storage": "ok"}}`; any failure → `503 {"error_code": "NOT_READY", "message": …, "request_id": …, "checks": {…: "fail"}}` |

- Both live at the root (not under `/api/v1`), need no authentication, and never include exception text, hostnames or credentials in the body (failure detail goes to the log only).
- Logic lives in `services/health.py`; the router only maps the result to a status code.
- Daemons do not get HTTP probes in this phase; their liveness is `spnc_daemon_last_success_timestamp_seconds` on the metrics port. Wiring compose `healthcheck:` entries to these endpoints is a follow-up for the compose owner (§7).

### 3.4 Structured logs (D6)
- New `app/core/logging.py`: `configure_logging()` used by the API launcher and all four daemons (replaces their `basicConfig`). Output: one JSON object per line on stdout with `ts` (UTC ISO-8601), `level`, `logger`, `msg`, plus `request_id` when set and any of `session_id`, `run_id`, `submission_id`, `exam_id`, `execution_generation`, `daemon` passed as context. `LOG_FORMAT=text` gives the old human format for local development; `LOG_LEVEL` sets the level.
- `request_id` is carried in a `contextvars.ContextVar` set by the middleware, so every log call during a request gets it without passing it around.
- One access-log line per request: `method`, `route` (template), `status`, `duration_ms`, `request_id`. **No query string, no headers, no body.**
- Request id hygiene (F5): a client `X-Request-ID` is kept only if it matches `^[A-Za-z0-9._-]{1,64}$`; otherwise a new UUID is generated.
- Generic exception handler (F6): an unhandled exception is logged once with its traceback and `request_id`, and the client gets `500 {"error_code": "INTERNAL_ERROR", "message": "Internal server error", "request_id": …}` with no exception text.
- `print()` in `queue.py` becomes `logger.error` with `run_id` / `submission_id` (F4). Existing f-string log messages are kept; ids are added as context fields where the call already has them.

### 3.5 Log hygiene (D7, PROJECT_RULES #25)
- Never logged: passwords, access/refresh tokens, `Authorization` / `Cookie` headers, `SECRET_KEY`, S3 keys, database URLs with credentials, request/response bodies, student source code, stdin/stdout of runs, trace payloads, scratchpad content, hidden test cases.
- Defence in depth: a logging filter in `configure_logging()` masks, in the final message and any string context field, (a) `Bearer <token>`, (b) JWT-shaped strings `eyJ….….…`, (c) `scheme://user:password@` URL credentials, (d) `password=`/`secret=`/`token=` key-value pairs. The filter is a safety net, not the mechanism: code must not pass such data to the logger in the first place.
- A regression test drives login, refresh, password change, trace ingest, snapshot and run requests with known marker values and asserts that none of the markers appears in the captured log output.

---

## 4. Invariants
1. Metrics and logs are never read by application logic; removing them changes no API response or database row.
2. No metric label contains a user id, session id, run id, raw URL path, or any free text — only bounded enumerations (route template, method, status, outcome, kind, reason, daemon).
3. `/metrics` is never served on the public API port; the metrics port is not published outside the host/internal network.
4. `/health` and `/ready` responses contain no secrets, hostnames or exception text; `/ready` failures still follow PROJECT_RULES #29.
5. The API runs one process per container while metrics use the in-process registry; going multi-worker requires multiprocess mode first.
6. No log line contains the data listed in §3.5.

---

## 5. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-17-01 | `GET /health` → 200 with no dependencies; `GET /ready` → 200 when DB/Redis/storage are up and 503 `NOT_READY` (with `request_id`, no exception text) when each one in turn is made unreachable. |
| AC-17-02 | After exercising trace ingest (accepted, duplicate retry, conflict), snapshot upload failure, a missing blob, an orphan sweep, a fencing rejection, a claim conflict and a WebSocket auth rejection, the corresponding counters in §3.1 increase by the expected amount. |
| AC-17-03 | HTTP metrics use the route template; requests to two different session ids produce one label set. |
| AC-17-04 | The metrics listener of a daemon process serves Prometheus text on `METRICS_PORT`; `METRICS_PORT=0` starts nothing; the public app has no `/metrics` route. |
| AC-17-05 | Every log line emitted during a request is valid JSON and carries that request's `request_id`; an invalid client `X-Request-ID` is replaced; an unhandled exception yields 500 `INTERNAL_ERROR` with `request_id` and a logged traceback. |
| AC-17-06 | The log-hygiene test (§3.5) finds none of the marker passwords, tokens, source code or trace payload values in captured logs; the redaction filter masks each pattern in a direct unit test. |
| AC-17-07 | Full `scripts/ci/regression.sh all` green locally on a fresh PostgreSQL; `ci` green on the PR; compose E2E (on `main`) additionally checks `/health` and `/ready`. |

---

## 6. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | Metrics library and format | (a) `prometheus_client` (official Python client, pinned), Prometheus text exposition; (b) OpenTelemetry SDK + OTLP exporter; (c) hand-written counters in Redis/PostgreSQL | **(a)**. De-facto standard, one small pure-Python dependency, scraped by Prometheus/Grafana Agent/VictoriaMetrics alike. (b) is heavier and needs a collector; (c) puts operational data in the source-of-truth stores. |
| **D2** | Which metrics in this phase | (a) the set in §3.1: every docs/07 metric that maps to an existing code path, plus HTTP and daemon-cycle metrics; deferred ones listed as follow-ups; (b) all of docs/07 §4, including new detection logic (sequence-gap analysis, delivery ids, pool stats); (c) HTTP and health only | **(a)**. Counts what the code already decides; (b) adds behaviour to a phase that should change none. |
| **D3** | How daemons (separate processes, F8) expose metrics | (a) each process serves its own registry on an internal `METRICS_PORT` (pull, one scrape target per container); (b) daemons push to a Prometheus Pushgateway; (c) daemons write counters to Redis and the API exports them | **(a)**. No extra service, no shared state; a dead daemon shows up as a failed scrape plus a stale `last_success` timestamp. (b) hides dead daemons behind last-pushed values. |
| **D4** | Health endpoints | (a) `/health` liveness (no checks) + `/ready` readiness (DB, Redis, storage), root path, no auth, no detail in body, 503 `NOT_READY` per rule #29; (b) a single `/health` that checks everything; (c) under `/api/v1/…` behind ADMIN auth | **(a)**. Orchestrators need unauthenticated probes, and a liveness probe that fails on a database blip would restart healthy API containers. |
| **D5** | Where `/metrics` is exposed | (a) separate internal port 9100 in every process, never on the public port, no auth; network isolation is the control; (b) `/metrics` on the public API port behind a bearer token `METRICS_TOKEN`; (c) public port, no auth | **(a)**. Same mechanism for API and daemons, needs no compose change now, and the public surface does not grow. (b) is the fallback if a future host cannot isolate the port. |
| **D6** | Log format and correlation | (a) JSON lines via a stdlib `logging` formatter (no new dependency), `request_id` from a contextvar, one access-log line per request without query string, `LOG_FORMAT=text` for local use, uvicorn access log off; plus request-id validation (F5) and a generic 500 handler (F6); (b) `structlog`; (c) keep text logs and only add `request_id` | **(a)**. Covers docs/07 §4.7 with standard library only; F5/F6 are required once ids are logged. |
| **D7** | Enforcing "never log secrets / student content" (PROJECT_RULES #25) | (a) explicit never-log list (§3.5) + redaction filter as safety net + automated marker test over real request flows; (b) list and review only; (c) filter only | **(a)**. The rule becomes testable; the filter catches accidents, the test catches regressions. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before any code is written.

---

## 7. Verification Record

_Empty until implementation._
