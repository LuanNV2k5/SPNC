# 48 — TEACHER PROBLEM AUTHORING UI

> **Status:** IMPLEMENTED — VERIFIED  
> **Date:** 2026-10-30  
> **Parent baseline:** `phase-20b-teacher-observation-locked` (`2b2bd80`)

## 1. Scope

This phase adds the teacher-facing workflow requested after Phase 20B:

- list and filter the teacher's problems;
- create, edit and soft-delete a problem;
- create, edit and delete sample/hidden test cases;
- publish/unpublish a problem to the teacher's classes;
- expose the workflow in the teacher navigation;
- prove that a published CLASS problem becomes visible in the enrolled student's practice list.

Exam authoring, student exam screens and admin UI remain separate phases.

## 2. API addition

The existing API could create and delete a `ProblemClassPublication` but could not read the current publication state. The UI therefore could not restore its state after a reload.

`GET /api/v1/problems/{problem_id}/publications`

- TEACHER owner only;
- returns `{items, total}` using the existing `PublicationResponse` shape;
- no migration and no change to publication semantics;
- cross-teacher reads return `403 PROBLEM_FORBIDDEN`.

The committed OpenAPI document and generated TypeScript client are regenerated with this additive endpoint.

## 3. UI routes

| Route | Purpose |
|---|---|
| `/teacher/problems` | List, filters, delete and entry to create/edit |
| `/teacher/problems/new` | Create problem |
| `/teacher/problems/{problemId}` | Content, test cases and class publication tabs |

All calls use the generated `openapi-fetch` client. Backend authorization remains authoritative.

## 4. Verification

| Check | Result |
|---|---|
| ESLint | PASS |
| TypeScript strict typecheck | PASS |
| Vitest | PASS — 43 tests |
| Production build | PASS |
| Backend problem-management regression | PASS — 16 PostgreSQL tests |
| Backend testcase regression | PASS — 7 PostgreSQL tests |
| Playwright authoring flow | PASS — teacher creates a CLASS problem, adds a sample, publishes it and the enrolled student sees it |

The production build retains the existing Monaco bundle-size warning; this phase does not increase or change Monaco packaging.
