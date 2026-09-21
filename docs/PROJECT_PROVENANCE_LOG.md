# Project Provenance Log

## Incident: Historical QA report artifact loss

Date:
2026-09-21

Affected files:

- PHASE_03_AUTH_RBAC_BUILD_REPORT.md
- PHASE_03_INDEPENDENT_QA_REPORT.md
- PHASE_03_INDEPENDENT_QA_REPORT_FINAL.md
- PHASE_03_REMEDIATION_REPORT.md
- PHASE_04_REMEDIATION_REPORT_1.md

Status for each:

LOST_UNTRACKED_ARTIFACT

Cause:

An overly broad QA cleanup command matching PHASE_* removed the files.

Recovery:

Exact copies were searched for in the local repository and available
Antigravity brain/report directories.

No exact surviving copies were found.

Important provenance statement:

- These reports were untracked artifacts.
- They were not members of the locked Phase03 or Phase04 commits.
- Their loss does not modify the locked source/test/migration history.
- Historical Git tags remain authoritative for locked baselines.
- Original report contents are NOT reconstructed or fabricated.
- Future audits must treat the original report contents as unavailable.

Authoritative effective baseline tags:
- phase-03-auth-rbac-complete: d4d496be0e4785f5fc88f231486a759220c42c00
- phase-04-admin-locked: 27b0fc8c15a0734c810f7cb4b2479f6eaa8cdc0f
- phase-05-academic-locked: a92af65361ce62c62df7a50e75b347e6b55f18b5

Future cleanup policy:

- Never use broad deletion patterns such as PHASE_*.
- Never use git clean for project QA cleanup.
- Temporary QA files must be explicitly named and removed individually.
- Historical reports/artifacts must be classified before deletion.
- Git locked tags/commits remain the authoritative implementation
  provenance.
- Untracked reports are supplementary evidence only.
