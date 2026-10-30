# SPNC web client (`apps/web`)

React + TypeScript + Vite single-page app (docs/46). Phase 20A: login, refresh-token rotation, forced password change, role routing, and the student practice flow with keystroke-level trace capture.

## Layout
| Path | Content |
|---|---|
| `src/api/` | `schema.d.ts` (generated, do not edit), `client.ts` (openapi-fetch, `X-Request-ID`, 401 → refresh → one retry), `auth.ts` (tokens, cross-tab single-flight refresh), `errors.ts`, `traceTransport.ts` |
| `src/trace/` | Pure TypeScript trace module, no UI imports (lint-enforced): recorder, IndexedDB store, payload builders, backoff, single-writer lock, client contract fixture |
| `src/features/auth/` | Login, change password, auth context |
| `src/features/practice/` | Problem list, problem page, Monaco workspace (checkpoint, run, submit) |
| `src/ui/` | Layout, route guards, error display |
| `src/i18n/vi.ts` | Every user-facing string (Vietnamese) |
| `e2e/` | Playwright tests against the compose stack |

## Commands
```bash
npm ci
npm run dev         # http://127.0.0.1:5173, /api proxied to SPNC_API_TARGET (default http://127.0.0.1:8000)
npm run lint
npm run typecheck
npm test            # Vitest
npm run build
npx playwright test # see docs/RUNBOOK.md §11
```

## Regenerating the API client
From the repository root, with the API's Python dependencies installed:
```bash
python scripts/web/dump_openapi.py
```
then `npm run gen:api` here, and commit `openapi.json` and `src/api/schema.d.ts`. CI fails when they are stale.

## Changing a trace payload
Payloads are built in `src/trace/payloads.ts` only. After a deliberate change, run `UPDATE_CONTRACT=1 npm test` to rewrite `src/trace/contract-fixtures.json`; the backend test `apps/api/tests/api/test_phase20a_trace_contract.py` posts that batch to the real ingest endpoint.

Dependencies are pinned to exact versions (`.npmrc` `save-exact=true`).
