# 46 — FRONTEND FOUNDATION AND STUDENT PRACTICE (PHASE 20A) SPECIFICATION

> **Module:** web client (`apps/web`): foundation, authentication, student practice flow with trace capture
> **Status:** APPROVED 2026-10-29 (all §6 recommendations; see PROJECT_PROVENANCE_LOG.md)
> **Date:** 2026-10-29
> **Parent Baseline:** `phase-19-retention-locked` (`5c77f97`; `main` = `5c92774`, docs-only roadmap PR #9 on top)
> **Proposed Branch:** `phase20a`
> **Target Lock Tag:** `phase-20a-frontend-foundation-locked`
> **Phase split (ROADMAP §2):** 20A foundation + student practice (this document) → 20B teacher session timeline and signals → 20C exams → 20D admin and statistics

---

## 1. Purpose

The backend is complete and locked through Phase 19, but there is no client: students cannot practise and the digital trace — the core of the project — is only ever produced by tests. Phase 20A delivers the smallest web client that produces **real trace data from a real editor**:

- a single-page app in `apps/web` with login, refresh-token rotation, forced password change, role-based routing and a uniform error display (`{error_code, message, request_id}`, PROJECT_RULES #29);
- the student practice flow: problem list → problem view → code editor that captures trace events → periodic checkpoint snapshots → Run with result → Submit with verdict;
- a **trace module** that never loses, reorders or duplicates events, including across network failures and page reloads;
- the decision on how the browser reaches the API (ROADMAP §2), so the backend needs **no change** in this phase.

Teacher, exam and admin screens are out of scope (20B–20D). Go-live gate G1 (ROADMAP §3) is unaffected: 20A runs only with test or demo data.

---

## 2. Findings (2026-10-29)

| # | Finding | Evidence | Impact |
|---|---|---|---|
| F1 | No CORS middleware and no reverse proxy; the API publishes `127.0.0.1:${API_PORT:-8000}` only. A page on another origin (Vite on `:5173`) is blocked. | `app/main.py` (no `CORSMiddleware`); `docker-compose.yml` `api.ports` | The client must be served same-origin, or the backend gains CORS (ROADMAP §2) |
| F2 | Architecture docs name **Next.js** for the web container. Nothing in the backend needs server-side rendering; every page is behind login. | `docs/07` l.50, `docs/10` l.10 | Choosing a plain SPA deviates from docs/07/10 and needs explicit approval (D1) |
| F3 | Auth is bearer-only: `POST /api/v1/auth/login` (OAuth2 **form** body) returns `access_token` (15 min) + `refresh_token` (7 days) in JSON; no cookies. `POST /auth/refresh` rotates; presenting an already-rotated token **revokes the whole family** (`REFRESH_REVOKED`). An expired/invalid access token → 401 `TOKEN_INVALID`. | `endpoints/auth.py`, `services/auth.py:139-149`, `api/deps.py`, `core/config.py:31-33` | Two tabs refreshing the same token at once log the user out everywhere → refresh must be single-flight **across tabs** (D7) |
| F4 | Forced password change: `GET /auth/me` returns `force_password_change`; every role-guarded endpoint returns 403 `PASSWORD_CHANGE_REQUIRED` until `POST /auth/change-password`, which also **revokes all refresh sessions** of the user. | `api/deps.py:111-119`, `endpoints/auth.py` `change_password` | After a successful change the client must log in again (it can do so silently with the new password it just sent) |
| F5 | Every error body is `{error_code, message, request_id}` (+ `details` on 422); the response header `X-Request-ID` echoes a client-supplied id matching `^[A-Za-z0-9._-]{1,64}$`. Server messages are English. | `app/main.py` handlers and middleware | The client can generate the request id itself, so even a failed/timeout request has an id to show; user-facing text needs a code → Vietnamese mapping |
| F6 | Trace ingest: `POST /my/coding-sessions/{id}/trace-events/batch`, ≤ 1000 events, `sequence_number ≥ 1`. Idempotent on `(session_id, sequence_number)` with a SHA-256 fingerprint of `event_type` + `payload` (**not** `client_timestamp`): identical resend → accepted 0; same sequence with different content → 409 `TRACE_SEQUENCE_CONFLICT`, whole batch aborted. Response carries `highest_contiguous_sequence` / `next_expected_sequence`. `GET …/trace-state` adds `checkpoint_interval_seconds` (default 60). | `endpoints/trace.py`, `services/trace.py`, `schemas/trace.py`, `docs/31` | A retried batch must be byte-identical in `event_type`/`payload`; payloads are frozen when an event is created |
| F7 | Client may send `PROBLEM_OPENED`, `EDITOR_CHANGED`, `SNAPSHOT_CREATED`, `RUN_REQUESTED`, `RUN_COMPLETED`, `SESSION_CHECKPOINT`. `SESSION_ENDED` and `SUBMISSION_CREATED` are server-only (422 `TRACE_EVENT_TYPE_RESERVED`). A `SESSION_CHECKPOINT` must reference an existing CHECKPOINT snapshot of the same session (422 `CHECKPOINT_SNAPSHOT_INVALID`). The server writes no `PROBLEM_OPENED`, `RUN_REQUESTED` or `RUN_COMPLETED` itself. | `models/trace.py:11-19`, `services/trace.py:23-41` | REQ-TRACE-001/011 are met only if the client emits these events; a checkpoint event is enqueued only after its snapshot is created |
| F8 | The server does **not** validate `EDITOR_CHANGED` payloads. The domain fixes the shape: `operation_type ∈ {INSERT, DELETE, REPLACE}`, `range_offset`, `range_length`, `text`, `editor_version`, optional `input_source`; diffs only, never full code (REQ-TRACE-003/004). Signals and the teacher timeline treat `EDITOR_CHANGED`, `RUN_REQUESTED`, `SUBMISSION_CREATED` as "meaningful" activity (idle detection). | `docs/01_DOMAIN.md` l.178-213; `docs/03` REQ-TRACE-003/004; `repositories/observation.py:21-25` | The client is the only enforcement of the payload contract in 20A (D9); server-side validation is a backend follow-up |
| F9 | **Submit ends the session** and writes `SUBMISSION_CREATED` at `max(sequence)+1`; ending writes `SESSION_ENDED` the same way. After that, new client events → 403 `SESSION_NOT_ACTIVE`; a client event with the sequence the server just took → 409. `POST …/end` accepts `last_sequence_number` and returns 409 `TRACE_NOT_FLUSHED` if the server has less; submit has no such guard. | `services/submission.py:78-90`, `services/session_lifecycle.py:45-80`, `schemas/academic.py` `EndSessionRequest` | The client must **flush the queue before submit/end** and send `last_sequence_number` on end; otherwise trailing events are lost |
| F10 | Practice endpoints: `GET /my/practice/problems` (paginated, PUBLIC + own classes), `GET /problems/{id}`, `POST /my/practice/sessions {problem_id, language ∈ CPP17/PYTHON3}` (403 `ACTIVE_EXAM_IN_PROGRESS`, 422 `LANGUAGE_NOT_SUPPORTED`), `GET /my/practice/sessions[/{id}]`, `POST …/{id}/end`. Starting does **not** reuse an existing ACTIVE session; stale ACTIVE sessions become ABANDONED after `SESSION_STALE_HOURS` (24). | `endpoints/academic.py:605-700`, `services/academic.py:440-480` | The client decides when to resume vs start a session (D10) |
| F11 | Run = `POST /my/coding-sessions/{id}/snapshots {reason: RUN, …}` then `POST …/{id}/runs {snapshot_id, input}`; result by polling `GET …/runs/{run_id}` (`PENDING → RUNNING → COMPLETED / FAILED_INTERNAL`). Submit = snapshot `SUBMIT` then `POST …/submissions {snapshot_id}` (201, `PENDING`); result via `GET /my/submissions/{id}` (`verdict`, `score`, `judge_result`, `result_visible`). No student push channel: the only WebSocket is `/api/v1/ws/teacher`. | `endpoints/run.py`, `endpoints/submission.py`, `schemas/run.py`, `schemas/academic.py:359-380`, `endpoints/ws.py` | Results are polled in 20A |
| F12 | Students have no endpoint to read their own snapshot **content**. | `endpoints/trace.py` (teacher-only snapshot reads in `observation.py`) | After a reload the editor content can only come from the browser's own storage (D8, D10) |
| F13 | The WebSocket authenticates by a first message `{"type":"auth","access_token":…}` (never in the URL) and does **not** check `Origin`. Auth is bearer-only, so a cross-site page cannot authenticate without already holding the token (no ambient cookie credential, i.e. no cross-site WebSocket hijacking). It is teacher-only and first used in 20B. | `endpoints/ws.py:1-63` | No `Origin` check is needed for 20A (D6); 20B re-evaluates |
| F14 | CI: matrix `tests` (6 backend groups) → aggregate job `ci` (the required check, `needs: tests`); `compose-e2e` runs only on push to `main`, nightly and on dispatch, never on PRs. `scripts/ci/regression.sh` is backend-only. | `.github/workflows/ci.yml`; docs/42 | A `web` job folds into `ci` via `needs`; browser E2E follows the compose-e2e cadence (D11) |
| F15 | FastAPI serves `/openapi.json`, but the schema can be produced without a server (`app.openapi()`), and the compose stack is not needed for client generation. | `app/main.py` (default FastAPI settings) | Client generation and the staleness check run in a plain CI job (D3) |

---

## 3. Scope

### 3.1 Application skeleton (`apps/web`)
- Vite + React + TypeScript (strict), React Router, TanStack Query, Mantine, `@monaco-editor/react` with Monaco bundled locally (no CDN loader), per D1–D5.
- Node 22 LTS; npm with a committed `package-lock.json`; every dependency pinned to an exact version (`save-exact`).
- Layout: `src/api/` (generated schema + typed client + auth/refresh), `src/trace/` (pure TS, §3.5), `src/features/{auth,practice}/`, `src/ui/` (error display, layout), `src/i18n/vi.ts` (all user-facing strings, Vietnamese).
- ESLint (`no-restricted-imports`: nothing under `src/trace/` may import React, Mantine, Monaco or `src/features`), Prettier, `tsc --noEmit`.

### 3.2 API access (D3, D6)
- `scripts/web/dump_openapi.py` writes `app.openapi()` to `apps/web/openapi.json` (committed); `openapi-typescript` generates `src/api/schema.d.ts` (committed); `openapi-fetch` is the only HTTP client for REST calls.
- Every request sends `X-Request-ID` = a fresh UUID generated by the client.
- Base path `/api/v1` relative to the page origin. Development: Vite dev-server proxy `/api` → `http://127.0.0.1:8000` (`ws: true`). Production: NGINX (§3.7).

### 3.3 Authentication (D7)
- Login form → `POST /auth/login` (form-encoded). Access token kept **in memory only**; refresh token in `localStorage`.
- On 401 `TOKEN_INVALID`: one refresh, then the original request is retried once. Refresh is **single-flight across tabs** via the Web Locks API (`navigator.locks.request("spnc-auth-refresh")`): inside the lock the tab re-reads `localStorage`; if another tab already rotated, it uses the new token instead of rotating again. Other tabs pick up new tokens via the `storage` event.
- `REFRESH_REVOKED`, `TOKEN_EXPIRED`, `ACCOUNT_*` on refresh → local logout with a message.
- Logout: flush trace (§3.5), `POST /auth/logout`, clear tokens and this user's IndexedDB data (§3.5.6).
- Forced password change: after login the client reads `/auth/me`; if `force_password_change`, every route redirects to `/change-password`. On success (all sessions revoked by the server, F4) the client logs in again with the new password and continues.

### 3.4 Routing and errors
- Routes: `/login`, `/change-password`, `/practice` (problem list), `/practice/problems/:problemId` (problem view + editor), `/` → role home. STUDENT → `/practice`; TEACHER and ADMIN → a placeholder "available in a later version" page with logout. Route guards are UX only; authorization stays on the backend (PROJECT_RULES #9, REQ-AUTH-006).
- Error display: one component renders `error_code`, a Vietnamese text for known codes (fallback: the server `message`), and `request_id` with a copy button. Network failures and timeouts show the client-generated request id with `error_code = NETWORK_ERROR`. 422 `details` are shown per field on forms. No token, password or code content is ever logged to the console or sent anywhere (PROJECT_RULES #25).

### 3.5 Trace module (`src/trace/`, D8, D9)
A pure TypeScript module with no UI imports. One `TraceRecorder` per coding session; the editor adapter (in `features/practice`) translates Monaco changes into recorder calls.

1. **Sequence numbers.** Allocated by the recorder, 1-based, strictly increasing, never reused. On open: `next = max(server next_expected_sequence, local max persisted sequence + 1)`.
2. **Persist-before-send.** Every event is written to IndexedDB (store `trace_pending`, key `[session_id, sequence_number]`) **before** it is eligible for sending; its `event_type` and `payload` are frozen at creation, so a resend is byte-identical (F6).
3. **Batching.** Flush when 50 events are pending, 2 s after the first unsent event, on `visibilitychange → hidden`, and on demand (run, submit, end, logout). Batch ≤ 200 events, contiguous, in sequence order. One request in flight per session.
4. **Acknowledgement.** After a 200, events up to `highest_contiguous_sequence` that were in the batch are deleted from IndexedDB.
5. **Retry.** Network error, timeout, 429, 5xx, 503 → exponential backoff 1 s → 30 s with jitter, unlimited while the page is open. 401 → auth refresh (§3.3) then resend. 403 `SESSION_NOT_ACTIVE` / `EXAM_*` → the session is closed: stop recording, keep the remaining events for diagnosis, tell the user. 409 `TRACE_SEQUENCE_CONFLICT` and 422 → stop sending for the session (a client bug), surface the error with its `request_id`; events are kept, not dropped.
6. **Reload / crash recovery.** IndexedDB also keeps the latest editor content per session (`drafts`, overwritten at most once per second). On reopening a session, pending events are resent first, then recording continues. On logout or after the session ended and the queue is empty, the user's stores are cleared; if events are still unsent at logout, the user is warned and may cancel.
7. **Single writer.** A Web Lock `spnc-trace-<session_id>` is held while a tab records a session; a second tab opening the same session shows "đang mở ở tab khác" and is read-only.
8. **Best effort on close.** On `pagehide` one `fetch(..., {keepalive: true})` flush is attempted; correctness does not depend on it (rule 2).
9. **Flush barrier.** `flush(): Promise<lastAckedSequence>` resolves only when the queue is empty; submit and end call it first (F9). If it cannot complete, submit/end are blocked with a retry prompt.

### 3.6 Student practice flow (D9, D10)
- **List:** `GET /my/practice/problems` with difficulty/language filters and pagination.
- **Open:** `GET /problems/{id}`; language picker from `supported_languages`. Resume or start per D10; on a new session the first event is `PROBLEM_OPENED`.
- **Edit:** each Monaco content change → one `EDITOR_CHANGED` per change range (D9).
- **Checkpoint:** every `checkpoint_interval_seconds`, only if the content changed since the last snapshot: `POST …/snapshots {reason: CHECKPOINT}` then enqueue `SESSION_CHECKPOINT {code_snapshot_id}`. A failed checkpoint (e.g. 503 `STORAGE_UNAVAILABLE`) is skipped and retried at the next interval.
- **Run:** snapshot `RUN` → `POST …/runs {snapshot_id, input}` → enqueue `RUN_REQUESTED` → poll `GET …/runs/{id}` (1 s, up to 60 s) → enqueue `RUN_COMPLETED` → show status, verdict, execution time and `testcase_results` (`RunResponse` has no top-level stdout/stderr).
- **Submit:** confirm dialog ("nộp bài sẽ kết thúc phiên") → `flush()` → snapshot `SUBMIT` → `POST …/submissions` → recorder closes → poll `GET /my/submissions/{id}` (2 s, up to 120 s) → show verdict, score and visible test results (respect `result_visible`).
- **Leave:** an explicit "Kết thúc" button → `flush()` → `POST …/end {last_sequence_number}`. Navigating away without it leaves the session ACTIVE (resumable per D10; the stale sweep ends it after 24 h).

### 3.7 Production serving (D6)
- `apps/web/Dockerfile`: multi-stage (Node build → `nginx` unprivileged image, pinned by digest) serving `dist/` with SPA fallback to `index.html`.
- `apps/web/nginx.conf`: `location /api/` → `http://api:8000` (path unchanged, `Upgrade`/`Connection` headers forwarded for `/api/v1/ws/`, `X-Request-ID` passed through); `/docs`, `/openapi.json`, `/health`, `/ready` and port 9100 are **not** proxied. Security headers: `Content-Security-Policy: default-src 'self'; script-src 'self'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`. Hashed assets cached long, `index.html` `no-cache`.
- `docker-compose.yml` gains one service `web` (build `apps/web`, `127.0.0.1:${WEB_PORT:-8080}:8080`, `depends_on: api`). No existing service changes. TLS stays a deployment concern (docs/10), outside 20A.

### 3.8 Tests and CI (D11)
- **Vitest** (jsdom + `fake-indexeddb`, fake timers, a scripted fake transport) for `src/trace/`: order; no loss under random network failures; no duplicates; retry/backoff; reload recovery (new recorder over the same IndexedDB resends and continues the sequence); flush barrier; 409/403/422 handling; single-writer lock. Also unit tests for the auth refresh single-flight and the error mapper.
- **Contract test** (backend side, existing pytest group `phase10plus`, no app code change): the payloads the client builds (exported fixtures) are accepted by the real ingest endpoint and a resend is accepted 0.
- **Playwright** (3 tests) against the compose stack including `web`: (1) admin-created student logs in, is forced to change password, lands on `/practice`; (2) open a problem, type, wait for a checkpoint, Run, Submit, see a verdict; afterwards the trace (read via the teacher replay API) is contiguous `1..N` and contains `PROBLEM_OPENED`, `EDITOR_CHANGED`, `SESSION_CHECKPOINT`, `RUN_REQUESTED`, `RUN_COMPLETED`, `SUBMISSION_CREATED`; (3) type while the network is blocked, reload, unblock: no gap, no duplicate, editor content restored.
- **CI:** new job `web` (`apps/web`): `npm ci`, lint, typecheck, Vitest, `vite build`, client staleness check (`dump_openapi.py` + `openapi-typescript`, then `git diff --exit-code`). The aggregate `ci` job becomes `needs: [tests, web]`, so the required check covers it without a branch-protection change. Playwright runs in a job `web-e2e` with the `compose-e2e` cadence (D11). `scripts/ci/regression.sh` stays backend-only.

### 3.9 Docs
`docs/RUNBOOK.md` gains "Web client" (dev server, build, `web` service, Playwright). `apps/web/README.md` (layout, regenerating the client). docs/07 and docs/10 are not edited (locked); this document supersedes their "Next.js" if D1 (a) is approved.

### 3.10 Out of scope
Teacher, exam and admin screens (20B–20D); scratchpad UI; student points page; any backend change, including CORS, cookie-based auth, payload validation for `EDITOR_CHANGED` and a student snapshot-read endpoint (backend follow-ups); WebSocket `Origin` check; TLS; i18n framework / English UI; load test (ROADMAP §4); accessibility audit beyond Mantine defaults; mobile layout.

---

## 4. Invariants
1. The backend is unchanged: no file under `apps/api/app` and no migration is modified in 20A.
2. The browser talks to the API only same-origin via `/api/v1`; no CORS, no direct database or storage access (PROJECT_RULES #8).
3. For every session, the sequence numbers the client sends are 1-based, strictly increasing, gap-free and never reused; a resend of a sequence carries identical `event_type` and `payload`.
4. An event is persisted in IndexedDB before it is sent and deleted only after the server acknowledged it; no error path deletes unacknowledged events silently.
5. Submit and end happen only after the trace queue of the session is empty.
6. `EDITOR_CHANGED` payloads carry diffs only, never full code; full code travels only in snapshots (REQ-TRACE-004).
7. No password, access token, refresh token or source code is logged or sent to any host other than the page origin; tokens never appear in URLs.
8. The trace module imports no UI code (lint-enforced).
9. Every displayed error carries `error_code` and a `request_id`.
10. The generated API client matches the backend's current OpenAPI schema (CI-enforced).

---

## 5. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-20A-01 | Login with valid credentials reaches the role home; wrong credentials show `INVALID_CREDENTIALS` with a request id; 429 `LOGIN_RATE_LIMITED` shows the retry time. |
| AC-20A-02 | A user with `force_password_change` can open no page other than `/change-password`; after changing, they are logged in again and land on the role home. |
| AC-20A-03 | An expired access token is refreshed transparently; two tabs hitting 401 at the same moment perform exactly one rotation and both stay logged in; a revoked refresh token logs out with a message. |
| AC-20A-04 | STUDENT sees the practice list; TEACHER/ADMIN see the placeholder; a direct URL to a student page as TEACHER shows the backend 403 rendered by the error component. |
| AC-20A-05 | Every error shown has `error_code`, text and a copyable `request_id`, including network failures. |
| AC-20A-06 | Trace unit tests: order, no loss, no duplicates, retry with backoff, reload recovery, flush barrier, 409/403/422 handling, single writer — all green. |
| AC-20A-07 | A full practice session (open, edit, ≥ 1 checkpoint, run, submit) produces on the server a contiguous trace `1..N` with the event types listed in §3.8 (2), `first_code_at` set, the CHECKPOINT/RUN/SUBMIT snapshots, a run result and a submission verdict shown in the UI. |
| AC-20A-08 | Editing while offline, reloading and reconnecting yields no gap and no duplicate on the server, and the editor shows the last content. |
| AC-20A-09 | Contract test: client payload fixtures are accepted by the ingest endpoint; resending a batch returns `accepted_count = 0`. |
| AC-20A-10 | `web` job green: lint, typecheck, Vitest, build, client up to date; `ci` requires `web`; a deliberately stale schema fails the job. |
| AC-20A-11 | Production image: SPA routes reload correctly, `/api/v1/...` and the WebSocket upgrade are proxied, `/docs` and `/metrics` are not reachable through `web`, the CSP header is present and Monaco works under it. |
| AC-20A-12 | Playwright 3 tests green against the compose stack (locally before lock, and in `web-e2e`); backend regression unchanged; `ci` green on the PR. |

---

## 6. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | Framework | (a) React + TypeScript + Vite, client-side SPA; (b) Next.js as named in docs/07/10 (F2); (c) Vue 3 + Vite | **(a)**. Every page is behind login, so SSR/SEO buys nothing; an SPA is a static build that NGINX serves next to the API with no Node process in production. React has the largest ecosystem for Monaco, Mantine and TanStack. (b) adds a Node server, a second routing model and same-origin plumbing for no gain here. Supersedes docs/07/10 "Next.js". |
| **D2** | Data fetching and routing | (a) TanStack Query + React Router; (b) Redux Toolkit + RTK Query; (c) plain `fetch` + React context | **(a)**. Query handles caching, polling (run/submit results) and retries declaratively; the only client-side state (auth, trace) lives in small dedicated modules, so a global store is unnecessary. (c) re-implements polling and cache invalidation by hand. |
| **D3** | API client | (a) generated from the backend OpenAPI schema with `openapi-typescript` + `openapi-fetch` (exact versions), schema dumped by `app.openapi()` without a server, generated files committed, CI fails when stale; (b) `orval` generating Query hooks; (c) hand-written types | **(a)**. Types follow the backend automatically and a backend change that breaks the client fails CI before merge. `openapi-fetch` is a ~6 kB wrapper with no runtime codegen; (b) generates far more code to review; (c) drifts silently. |
| **D4** | UI kit | (a) Mantine; (b) MUI; (c) Tailwind + shadcn/ui | **(a)**. Complete component set (forms, tables, notifications, modals) with no styling setup; good for speed. (b) is heavier; (c) means owning every component. |
| **D5** | Code editor | (a) Monaco via `@monaco-editor/react`, Monaco bundled locally (no CDN), Vite workers; (b) CodeMirror 6 | **(a)**. Its change events give exactly `rangeOffset`, `rangeLength`, `text` and a model version id — the fields REQ-TRACE-003 requires — and C++/Python support is built in. Local bundling keeps CSP `script-src 'self'` and works offline. (b) is lighter but needs more glue for the same trace fields. |
| **D6** | How the browser reaches the API (ROADMAP §2) | (a) same origin: Vite dev-server proxy `/api` → API in development, NGINX in the `web` image in production (§3.7); no CORS, no backend change; (b) CORS in the API with `CORS_ALLOW_ORIGINS`; (c) both | **(a)** (= ROADMAP option (b) for production, with the dev proxy instead of option (c)'s dev CORS). No backend change and no origin list to maintain. **WebSocket `Origin`:** not checked today (F13); since auth is a bearer token sent in the first message and no cookie is involved, a foreign page cannot open an authenticated socket. No check is added in 20A; 20B (first WebSocket user) re-evaluates and may add an allow-list. |
| **D7** | Token storage and refresh | (a) access token in memory; refresh token in `localStorage`; refresh single-flight across tabs with Web Locks + `storage` event; strict CSP; (b) refresh token in `sessionStorage` (per tab); (c) memory only (log in again after every reload); (d) httpOnly cookie (backend change) | **(a)**. A reload during practice must not log the student out. (b) breaks with duplicated tabs, which copy `sessionStorage` and trigger reuse detection (F3); (c) is safe but forces login on every reload; (d) is the strongest against XSS but changes the backend (out of scope; candidate for a later phase). The risk of (a) — script injection reading the token — is limited by the CSP and by rendering no user HTML. |
| **D8** | Trace module design | (a) pure TS module per §3.5: client-allocated sequences, persist-before-send in IndexedDB, batches ≤ 200 / 2 s / 50 events, backoff 1–30 s, flush barrier, single writer per session via Web Locks, user data cleared at logout; (b) same without IndexedDB (memory queue only); (c) send each event immediately | **(a)**. It is the only option that meets "no loss" across reload and crash, and IndexedDB also supplies the editor draft for resume (F12). Batching keeps 20 000 events/session to a few hundred requests (NFR-PERF-007/008). (b) loses whatever was unsent when the tab closes. |
| **D9** | Event payload contract (client side) | (a) client emits `PROBLEM_OPENED {problem_id, language}`; one `EDITOR_CHANGED` per Monaco change range `{operation_type, range_offset, range_length, text, editor_version, input_source: "typing"\|"paste"\|"other"}` (no coalescing); `SESSION_CHECKPOINT {code_snapshot_id}`; `RUN_REQUESTED {code_snapshot_id, run_id, input_used}`; `RUN_COMPLETED {run_id, code_snapshot_id, status, verdict, execution_time_ms}` (output and error detail of REQ-TRACE-011 stay on the run row that `run_id` references, not copied into the trace); not `SNAPSHOT_CREATED` (the snapshot row is the record). `client_timestamp` = ISO 8601 UTC; (b) as (a) but coalesce keystrokes within 300 ms into one event | **(a)**. Matches docs/01 and REQ-TRACE-001/003/011/013 field by field, keeps the trace replayable keystroke-by-keystroke, and the backend is sized for it (NFR-PERF-008). Paste is recorded as `input_source`, never as an operation type (docs/01 l.203). (b) loses fidelity and makes the payload a non-domain shape. Payload fixtures are shared with the backend contract test (AC-20A-09). |
| **D10** | Resume vs new session when a student opens a problem | (a) resume the newest ACTIVE practice session for that problem **if** this browser holds its draft and pending events; otherwise end that session (`POST …/end`) and start a new one; (b) always start a new session; (c) resume regardless and start from an empty editor | **(a)**. Reload and accidental tab close continue the same session (one coherent trace); on a different device the old session is closed cleanly instead of lingering 24 h. (c) would make the editor disagree with the trace. A backend endpoint returning the latest own snapshot would allow resume anywhere — backend follow-up. |
| **D11** | Test and CI scope | (a) Vitest + contract test + `web` job on every push/PR, folded into `ci` via `needs: [tests, web]`; Playwright 3 tests in job `web-e2e` with the `compose-e2e` cadence (push to `main`, nightly, dispatch), plus a mandatory local run recorded in §7 before lock; (b) as (a) but Playwright on every PR as part of `ci`; (c) no browser E2E | **(a)**. Follows the docs/42 precedent (compose stack is not built on PRs); the logic that can lose data (trace module) is covered on every PR by fast unit tests. (b) adds ~10 min and sandbox image pulls to every PR. |
| **D12** | UI language | (a) Vietnamese only, all strings in `src/i18n/vi.ts`, known `error_code`s mapped to Vietnamese text with the server `message` as fallback; (b) i18n library with vi + en | **(a)**. Users are Vietnamese students and teachers; one file keeps a later switch to a library cheap. |
| **D13** | Production serving | (a) `apps/web` Dockerfile (Node build → unprivileged NGINX) and one new compose service `web` on `127.0.0.1:${WEB_PORT:-8080}`, no change to existing services; (b) no compose change, NGINX config shipped as a file only, E2E against `vite preview` | **(a)**. The E2E tests then exercise the real production path (proxy, WebSocket upgrade, CSP). The change is additive; the running demo stack is untouched until an operator rebuilds it. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md` before any code is written.

---

## 7. Verification Record

### 7.1 Changes
| Commit | Content |
|---|---|
| `ce0b0b0` | This specification (draft) |
| `09fb721` | Spec approval (PROJECT_PROVENANCE_LOG) |
| `ce303c1` | `apps/web` scaffold (exact pins, ESLint rule for `src/trace`), `scripts/web/dump_openapi.py`, committed `openapi.json` + `src/api/schema.d.ts`, trace module (`recorder`, IndexedDB `store`, `payloads`, `backoff`, `lock`) with Vitest tests |
| `e356c65` | API client (`X-Request-ID`, 401 → refresh → one retry), cross-tab single-flight refresh (Web Locks), error display, Vietnamese strings, routing and guards, login, forced password change, practice list, problem page, Monaco workspace (trace capture, checkpoint, run, submit, end, resume per D10) |
| `faa952e` | `apps/web/Dockerfile` + `nginx.conf`, compose service `web`, `WEB_PORT` in `.env.example`; CI job `web` and `ci needs: [tests, web]`; Playwright step in `compose-e2e`; client contract fixture + `tests/api/test_phase20a_trace_contract.py` (group `phase10plus`); Playwright tests; RUNBOOK §11; `apps/web/README.md` |

### 7.2 Implementation Notes (within the approved decisions)
- **Versions.** The newest release of each major line that is known to work together: React 19.3.1, React Router 7.18.5, TanStack Query 5.105.0, Mantine 8.3.18, Vite 7.3.7, Vitest 4.1.12 (3.x has audit findings in `@vitest/mocker`/`tinypool`), TypeScript 5.9.3 (`openapi-typescript` 7 requires TypeScript 5), ESLint 10.13.0, `monaco-editor` 0.52.2, `openapi-fetch` 0.17.0, `openapi-typescript` 7.13.0, Playwright 1.64.1. `npm audit`: 0 vulnerabilities. CI uses Node 22.
- **Browser E2E placement (D11).** The Playwright tests run as a step of the existing `compose-e2e` job (same stack, same cadence: push to `main`, nightly, dispatch) rather than in a separate `web-e2e` job, so the stack is built once. The report is uploaded on failure.
- **Submit ends the session.** The server appends `SUBMISSION_CREATED` and then `SESSION_ENDED`; the client flushes before submit and calls `finish()` afterwards, which deletes the session's local data.
- **Trace fidelity.** Monaco's auto-indent whitespace is recorded as typed. The E2E tests therefore compare the replay of the server trace with the submitted (or run) snapshot content **exactly**, not with the rendered editor text.
- **Input source.** Paste is detected by a capturing DOM `paste` listener on the editor; undo/redo map to `other`; `isFlush` changes (initial content) are not recorded.
- **`PROBLEM_OPENED`** is recorded when the recorder opens a session with no events yet (a fresh session).
- **Run output.** `RunResponse` has no top-level stdout; the workspace shows `stdout`, `stderr`, `compile_error_message`, `runtime_error_message` from `testcase_results` when present.
- **Paths not proxied.** Through `web`, `/docs`, `/openapi.json`, `/health`, `/ready`, `/metrics` return the SPA shell (200 `text/html`), never the API.
- **Resume edge.** If a session's metadata is in IndexedDB but its draft is not yet written (closed within 1 s of the first keystroke), the editor resumes empty while the server trace has that keystroke. Accepted for 20A; a student snapshot-read endpoint (backend follow-up, §3.10) removes it.
- **Offline reload.** There is no service worker, so a reload with the network fully down cannot load the app shell; recovery happens on the next load. The E2E test simulates the failure by aborting only the ingest requests.
- **Bundle size.** The full Monaco build is bundled (main chunk about 1 MB gzip). Loading only the C++/Python contributions is deferred.

### 7.3 Verification
| Check | Environment | Result |
|---|---|---|
| AC-20A-06 Vitest (trace recorder, store, payloads, contract fixture, auth refresh single-flight, error mapping) | this machine, Node 24, jsdom + `fake-indexeddb` | **28 passed** |
| Lint, typecheck, production build | same | clean; build OK |
| AC-20A-10 generated client up to date | `dump_openapi.py` (FastAPI 0.141.1 = `requirements.txt`) + `npm run gen:api` | no diff |
| AC-20A-09 `test_phase20a_trace_contract.py` | own PostgreSQL 16 on port 55435 | **2 passed** |
| Full local regression `regression.sh all` | same, every group isolated | **595 passed, 0 failed** (48 files; 593 before this phase + 2) |
| AC-20A-11 production image through `web` | separate compose project `spnc20a` (ports 18000/18080/19001; demo stack `phase11` untouched) | SPA route reload 200 with CSP, `nosniff`; `/api/v1/auth/me` 401 with the client `X-Request-ID` echoed; WebSocket upgrade 101; `/docs`, `/openapi.json`, `/health`, `/ready`, `/metrics` return only the SPA shell |
| AC-20A-02/04/05/07/08/12 Playwright (4 tests) | same stack, Chromium | **4 passed**: forced password change and reload; teacher placeholder and `FORBIDDEN_ROLE` with request id; full practice session (checkpoint, run, submit ACCEPTED), server trace contiguous `1..N` with every event type, replay = submitted snapshot exactly; ingest failure + reload: no gap, no duplicate, replay = run snapshot exactly |
| AC-20A-03 two tabs | unit tests (serializing lock stand-in) | one rotation per tab burst; each rotation uses the newest stored token; not exercised with two real browser tabs |
| AC-20A-12 CI | GitHub Actions on the PR | _pending_ |
