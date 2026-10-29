# 42 — CONTINUOUS INTEGRATION & BRANCH PROTECTION (PHASE 16 / STEP 1) SPECIFICATION

> **Module:** GitHub Actions CI, protection of `main`, small technical-debt fixes
> **Status:** APPROVED 2026-10-29 (all §6 recommendations; see PROJECT_PROVENANCE_LOG.md) — IMPLEMENTATION IN PROGRESS
> **Date:** 2026-10-29
> **Parent Baseline:** `phase-15a-oq-review-locked` (`efdabd3`, = `main`)
> **Proposed Branch:** `phase16`
> **Target Lock Tag:** `phase-16-ci-locked`

---

## 1. Purpose

Every verification so far has run on one developer machine, by hand. Step 1 of the risk-ordered plan puts a safety net under all later work:
- every push and pull request is tested automatically on clean infrastructure;
- `main` changes only through a pull request with a green CI run.

**No application behaviour changes in this phase.**

---

## 2. Findings (2026-10-29)

| # | Finding | Impact |
|---|---|---|
| F1 | No CI. The 537-test regression (44 files, one fresh database per phase group) runs only on this machine, sequentially, about 25 minutes. | A regression can reach `main` unnoticed; results depend on one machine |
| F2 | `main` is unprotected. Commits are pushed to it directly; force-push and deletion are possible. | One mistaken push rewrites the baseline |
| F3 | The regression runner (database list, file → database mapping) lives in a scratch folder outside the repository. | Not reproducible by anyone else |
| F4 | `app/core/config.py` declares `class Settings` twice. The first copy (lines 1–30) is dead code because the second definition replaces it; edits to the first copy silently do nothing. | Trap for future edits |
| F5 | `app/schemas/run.py` and `app/schemas/trace.py` use the deprecated Pydantic `class Config`. Other test warnings come from third-party packages (Starlette/httpx test client, passlib/argon2). | Will break on Pydantic v3 |
| F6 | `gh` (GitHub CLI) is not installed on this machine, so pull requests cannot be opened from here, and branch protection cannot be set from here either. Public CI results can still be read through the GitHub REST API. | Affects the PR workflow (D5) |

The repository is **public**, so standard GitHub-hosted runners are free.

---

## 3. Scope

### 3.1 Regression runner in the repository (F3)
`scripts/ci/regression.sh`: creates every test database (PostgreSQL URL from the environment), migrates each to head, runs each test file on its own against its database (the mapping used for every phase so far), prints a per-file summary and exits non-zero on any failure or migration error. It takes a group name (`auth`, `academic`, `judge`, `signals`, `observation`, `phase10plus`, `all`) so CI can run groups in parallel and a developer can run everything locally.

### 3.2 Workflow `.github/workflows/ci.yml`
| Item | Detail |
|---|---|
| Triggers | `push` (all branches) and `pull_request` to `main`; `workflow_dispatch` |
| Job `tests` | Matrix over the runner groups (D2), `ubuntu-24.04`, Python 3.14 (same as the Dockerfile), pip cache. Services: `postgres:16-alpine`, `redis:7-alpine`. MinIO started with `docker run` (the Chainguard image needs a command, which service containers cannot take) for the `phase10plus` group. Sandbox images pre-pulled for the `judge` group. Timeout 30 min per group. |
| Job `ci` | Single required status check that passes only when every matrix group passed, so branch protection names one check. |
| Job `compose-e2e` | Builds the compose stack with a generated `.env`, bootstraps an admin, runs `tests/e2e/test_compose_stack.py`, tears down. Triggers per D3. |
| Concurrency | One run per ref; a new push cancels the previous run for that ref. |
| Secrets | None needed; test credentials are disposable and local to the runner. |

### 3.3 Branch protection for `main` (F2, D4)
- Require a pull request before merging; require status check `ci` to pass, with the branch up to date.
- Block force pushes and deletion; apply the rules to administrators too.
- Required approvals: per D4.

### 3.4 Technical debt (F4, F5)
- Delete the dead first `Settings` copy in `config.py`.
- Replace `class Config` with `model_config = ConfigDict(from_attributes=True)` in the two schemas.

---

## 4. Invariants
1. `main` only advances through a pull request whose `ci` check passed.
2. CI uses only disposable credentials; no repository secret is required or exposed.
3. The CI regression runs the same files, against the same per-group databases, as local verification.

---

## 5. Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-16-01 | `scripts/ci/regression.sh all` reproduces the local result (537 passed) on this machine. |
| AC-16-02 | A push of `phase16` triggers the workflow; every group passes on GitHub-hosted runners; `ci` is green (read from the public Actions API). |
| AC-16-03 | A deliberately failing test on a throwaway branch makes `ci` red (the check really gates), then the branch is deleted. |
| AC-16-04 | `compose-e2e` passes when triggered per D3. |
| AC-16-05 | Branch protection active on `main` as in §3.3; a direct push to `main` is rejected. |
| AC-16-06 | Tech-debt fixes in place; full regression still green. |

---

## 6. Decisions Requiring Project Owner Approval

| ID | Question | Options | Recommendation |
|---|---|---|---|
| **D1** | CI platform | (a) GitHub Actions on GitHub-hosted runners (free, public repo); (b) self-hosted runner | **(a)** |
| **D2** | How the regression runs in CI | (a) matrix of 6 groups in parallel (about 8–10 min wall time), every push and PR; (b) one sequential job (about 30 min); (c) fast subset without the Docker sandbox on branch pushes, full suite only on PRs | **(a)**. Every change gets the full suite, and parallel groups keep it quick. |
| **D3** | When the compose end-to-end job runs | (a) on pushes to `main`, nightly and on demand; (b) on every PR too; (c) on demand only | **(a)**. It builds images (slow); PRs already run the full regression. |
| **D4** | Branch protection | (a) PR required, `ci` required and up to date, no force push or deletion, applies to admins, **0 required approvals** (single maintainer); (b) the same with 1 required approval; (c) no protection | **(a)**. (b) is the right choice once there is a second reviewer. |
| **D5** | Who opens PRs and applies protection (F6) | (a) you install `gh` and run `gh auth login` once; I then open PRs, set protection through the API and watch CI; (b) you open PRs and set protection in the GitHub web UI, following the steps I give; I read CI results through the public API | **(a)**. Fewer manual steps per change. (b) works without installing anything. |
| **D6** | Include the tech-debt fixes (F4, F5) here | (a) yes; (b) separate phase | **(a)**. Small, and covered by the same CI run. |

Approval is recorded in `docs/PROJECT_PROVENANCE_LOG.md`. Setting branch protection changes repository settings, so it is done only after this approval (D5 decides by whom).

---

## 7. Verification Record

*To be completed at Phase 16 closure.*
