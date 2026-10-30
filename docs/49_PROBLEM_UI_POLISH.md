# Phase 20D — Problem authoring UI polish

> **Status:** IMPLEMENTED — VERIFIED 2026-10-30  
> **Parent work:** Phase 20C problem authoring UI

## Scope

Phase 20D turns the functional teacher problem-authoring prototype into a consistent application surface without changing its API contract or business behaviour.

- Responsive application shell with desktop sidebar and mobile navigation.
- Shared visual foundation: typography, colour, spacing, surfaces and status treatments.
- Teacher problem dashboard with summary cards, grouped filters, responsive table and intentional empty state.
- Three-step authoring workflow: content, test cases and publications.
- Two-column problem form with separated content and judging settings, field guidance and a sticky save action.
- Improved test-case code previews, creation layout and empty state.
- Improved publication chooser, status table and private-problem guidance.

No database migration or new backend endpoint is part of this phase.

## Verification

| Check | Result |
|---|---|
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm test` | 43 passed |
| `npm run build` | Passed; existing Monaco chunk warning remains |
| Playwright `AC-PROBLEM-UI-01` against isolated Compose demo | 1 passed |
| Manual browser verification | Problem list and create page rendered correctly |

Demo stack: `spncphase1demo`, web `http://127.0.0.1:38080`.
