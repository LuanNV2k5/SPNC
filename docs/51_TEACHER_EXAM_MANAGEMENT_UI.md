# Phase 21A — Teacher exam management UI

> **Status:** IMPLEMENTED — LOCAL CHECKS PASS; COMPOSE E2E PENDING  
> **Date:** 2026-10-30  
> **Baseline:** `phase-20e-ui-polish-locked` (`ae9f7b6`)

## 1. Scope

Add the teacher-facing exam management workflow to the existing React/Mantine client. This phase consumes the current exam APIs; it adds no backend behavior, database migration, or API endpoint.

- list teacher-owned exams and show lifecycle status;
- create an exam and edit its configuration while it remains a draft;
- assign/remove teacher-owned classes;
- attach/remove teacher-owned problems and set each maximum score;
- publish a draft exam or cancel a draft/scheduled exam with a reason;
- inspect paginated student participation status for an exam;
- add the exams section and routes to teacher navigation.

Student exam taking and admin/statistics screens remain separate work. This document records the implemented scope and acceptance checks; it does not establish ordering for later phases beyond the approved roadmap.

## 2. Routes and API integration

| Route | Purpose |
|---|---|
| `/teacher/exams` | List and enter exam management |
| `/teacher/exams/new` | Create an exam |
| `/teacher/exams/{examId}` | Configure, publish/cancel, and observe participation |

The client uses existing endpoints: `GET/POST /api/v1/exams`, `GET/PATCH /api/v1/exams/{exam_id}`, exam `/classes` and `/problems` collection routes, `/publish`, `/cancel`, and `/observation`. Authorization and lifecycle validation remain enforced by the API. No migration is required.

Only `DRAFT` exams can be configured. Publishing remains available only for drafts; cancellation is offered for drafts and scheduled exams. The backend remains authoritative for requirements such as having classes, problems and test cases before publication.

## 3. Acceptance checks

| ID | Check |
|---|---|
| AC-21A-01 | Teacher creates an exam from the UI, assigns a class and a problem with a score, publishes it, and sees the enrolled student as `NOT_STARTED` in observation. |
| AC-21A-02 | Frontend strict typecheck, ESLint, unit tests and production build pass. |
| AC-21A-03 | Compose Playwright E2E passes on the configured integration stack. |

## 4. Verification record

| Check | Result |
|---|---|
| `npm run typecheck` | PASS |
| `npm run lint` | PASS |
| `npm test -- --run` | PASS — 43 tests in 9 files |
| `npm run build` | PASS; existing Monaco bundle-size warning remains |
| `git diff --check` | PASS |
| Playwright AC-21A-01 | First Compose run reached the class picker, then exposed an ambiguous test locator (input and listbox both matched); selector corrected, rerun pending |
| Desktop/mobile visual review | Pending; requires a running app/API stack |
| CI / PR / merge / lock tag | Pending |

## 5. Remaining work to close this phase

1. Run `npx playwright test e2e/exam-management.spec.ts` against the Compose E2E stack and fix any failures.
2. Review the exam list and detail screens on desktop and mobile with a running app; this is functional QA, not a visual polish pass.
3. Run the repository CI on the final branch state, then complete the project's PR, merge, lock and tag steps when authorized.
