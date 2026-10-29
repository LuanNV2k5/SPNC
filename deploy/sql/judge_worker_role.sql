-- docs/40 Q4 (OQ-26): least-privilege PostgreSQL role for production judge workers.
--
-- Run as the database owner after `alembic upgrade head` (idempotent), then set a password:
--   ALTER ROLE spnc_judge PASSWORD '<secret>';
-- The judge host's DATABASE_URL uses spnc_judge. API, reconciler and schedulers keep the owner role.
--
-- The worker reads what it needs to grade (problems, test cases, snapshot metadata, exam
-- max scores) and writes only judge results, the exam total (D5) and practice points (OQ-16).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'spnc_judge') THEN
        CREATE ROLE spnc_judge LOGIN;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO spnc_judge', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO spnc_judge;

-- Read-only inputs
GRANT SELECT ON problems, problem_test_cases, code_snapshots, exam_problems TO spnc_judge;

-- The Phase 09C notify trigger on runs (runs as the invoking role) looks up the session's student
GRANT SELECT (id, student_id) ON coding_sessions TO spnc_judge;

-- Judge jobs: claim (CAS on status/generation) and fenced result writes
GRANT SELECT ON submissions, runs TO spnc_judge;
GRANT UPDATE (status, verdict, score, judge_result, execution_generation, lease_expires_at, updated_at)
    ON submissions TO spnc_judge;
GRANT UPDATE (status, verdict, execution_generation, lease_expires_at, execution_time_ms, execution_memory_kb,
              testcase_results, updated_at)
    ON runs TO spnc_judge;

-- docs/36 D5: best-score total per participation (row lock + update of the total only)
GRANT SELECT ON exam_participations TO spnc_judge;
GRANT UPDATE (total_score, updated_at) ON exam_participations TO spnc_judge;

-- OQ-16: practice point awards (append-only ledger). ON CONFLICT against the partial unique
-- index also needs SELECT on the columns PostgreSQL uses to infer it.
GRANT INSERT ON point_transactions TO spnc_judge;
GRANT SELECT (student_id, problem_id, reason) ON point_transactions TO spnc_judge;
