#!/usr/bin/env bash
# SPNC backend regression runner (docs/42 §3.1). Used by CI and locally.
#
#   scripts/ci/regression.sh [group]      group: auth | academic | judge | signals | observation | phase10plus | all
#   scripts/ci/regression.sh mapping      check that every test file belongs to a group
#
# Environment:
#   PYTHON   Python with apps/api/requirements.txt installed (default: python)
#   PG_BASE  PostgreSQL superuser URL without database (default: postgresql://spnc_test:spnc_test_password@localhost:5432)
#
# Each test file runs on its own against a freshly created, fully migrated database,
# the same way every phase has been verified since Phase 03.
set -uo pipefail

GROUP="${1:-all}"
PYTHON="${PYTHON:-python}"
PG_BASE="${PG_BASE:-postgresql://spnc_test:spnc_test_password@localhost:5432}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/apps/api"

# group -> "file database" pairs
group_files() {
  case "$1" in
    auth) cat <<'EOF'
tests/api/test_auth.py spnc_phase03_auth_test
tests/api/test_db_guard.py spnc_phase04_admin_test
tests/api/test_admin.py spnc_phase04_admin_test
EOF
    ;;
    academic) cat <<'EOF'
tests/api/test_academic.py spnc_phase05_academic_test
tests/api/test_trace.py spnc_phase06_trace_test
EOF
    ;;
    judge) cat <<'EOF'
tests/api/test_run.py spnc_phase07_judge_test
tests/judge/test_fencing.py spnc_phase07_judge_test
tests/judge/test_queue.py spnc_phase07_judge_test
tests/judge/test_adapters.py spnc_phase07_judge_test
tests/judge/test_sandbox_security.py spnc_phase07_judge_test
EOF
    ;;
    signals)
      for f in tests/db/test_db_invariants.py tests/judge/test_trace_outbox_schema.py tests/judge/test_signals_*.py tests/judge/test_scheduler_*.py; do
        echo "$f spnc_phase10_fresh"
      done
    ;;
    observation) cat <<'EOF'
tests/api/test_session_lifecycle.py spnc_phase08e_session_test
tests/api/test_observation.py spnc_phase09_observation_test
tests/api/test_annotations.py spnc_phase09_observation_test
tests/api/test_ws_notifications.py spnc_phase09_observation_test
EOF
    ;;
    phase10plus) cat <<'EOF'
tests/judge/test_grader.py spnc_phase10_submission_test
tests/api/test_testcases.py spnc_phase10_submission_test
tests/api/test_submissions.py spnc_phase10_submission_test
tests/judge/test_submission_fencing.py spnc_phase10_submission_test
tests/api/test_exam_lifecycle.py spnc_phase10_submission_test
tests/api/test_exam_timeout.py spnc_phase10_submission_test
tests/api/test_statistics.py spnc_phase10_submission_test
tests/api/test_storage_failures.py spnc_phase10_submission_test
tests/infra/test_storage_s3.py spnc_phase10_submission_test
tests/api/test_phase12a_classes_problems.py spnc_phase10_submission_test
tests/api/test_phase12b_exams.py spnc_phase10_submission_test
tests/api/test_phase12c_trace.py spnc_phase10_submission_test
tests/api/test_phase13a_snapshots.py spnc_phase10_submission_test
tests/api/test_phase13b_idle_threshold.py spnc_phase10_submission_test
tests/api/test_phase13c_checkpoint_practice.py spnc_phase10_submission_test
tests/api/test_phase14a_points.py spnc_phase10_submission_test
tests/infra/test_judge_isolation.py spnc_phase10_submission_test
tests/api/test_phase15a_oq_fixes.py spnc_phase10_submission_test
EOF
    ;;
    *) echo "unknown group: $1" >&2; return 1 ;;
  esac
}

if [ "$GROUP" = "mapping" ]; then
  # Every test file must belong to a group, or CI would silently skip it (e2e needs a running stack)
  MAPPED="$(for g in auth academic judge signals observation phase10plus; do group_files "$g"; done | awk '{print $1}' | sort -u)"
  ALL="$(find tests -name 'test_*.py' -not -path 'tests/e2e/*' | sort)"
  MISSING="$(comm -23 <(echo "$ALL") <(echo "$MAPPED"))"
  if [ -n "$MISSING" ]; then
    echo "Test files not assigned to any regression group:"; echo "$MISSING"; exit 1
  fi
  echo "All $(echo "$ALL" | grep -c .) test files are assigned to a regression group."
  exit 0
fi

if [ "$GROUP" = "all" ]; then
  GROUPS_TO_RUN="auth academic judge signals observation phase10plus"
else
  GROUPS_TO_RUN="$GROUP"
fi

PAIRS="$(for g in $GROUPS_TO_RUN; do group_files "$g" || exit 1; done)" || exit 2
DATABASES="$(echo "$PAIRS" | awk '{print $2}' | sort -u)"

echo "== Preparing databases: $(echo $DATABASES)"
for db in $DATABASES; do
  "$PYTHON" - "$PG_BASE" "$db" <<'PYEOF' || { echo "MIGRATE FAIL $db (create)"; exit 2; }
import sys
from sqlalchemy import create_engine, text
base, name = sys.argv[1], sys.argv[2]
eng = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
with eng.connect() as c:
    c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    c.execute(text(f'CREATE DATABASE "{name}"'))
PYEOF
  if ! DATABASE_URL="$PG_BASE/$db" "$PYTHON" -m alembic upgrade head > /dev/null 2>&1; then
    echo "MIGRATE FAIL $db"
    exit 2
  fi
done

FAILED=0
TOTAL_PASSED=0
SUMMARY=""
while read -r file db; do
  [ -z "$file" ] && continue
  out="$(DATABASE_URL="$PG_BASE/$db" TEST_DATABASE_URL="$PG_BASE/$db" "$PYTHON" -m pytest "$file" -q -p no:warnings 2>&1)"
  rc=$?
  last="$(echo "$out" | tail -1)"
  passed="$(echo "$last" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo 0)"
  TOTAL_PASSED=$((TOTAL_PASSED + ${passed:-0}))
  if [ $rc -ne 0 ]; then
    FAILED=$((FAILED + 1))
    echo "::group::FAILED $file"
    echo "$out" | tail -60
    echo "::endgroup::"
  fi
  line="$file [$db]: $last"
  echo "$line"
  SUMMARY="$SUMMARY$line"$'\n'
done <<< "$PAIRS"

echo
echo "== Group(s): $GROUPS_TO_RUN | files: $(echo "$PAIRS" | grep -c .) | passed: $TOTAL_PASSED | failed files: $FAILED"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  { echo "### Regression: $GROUPS_TO_RUN"; echo '```'; printf '%s' "$SUMMARY"; echo '```'; echo "**passed: $TOTAL_PASSED, failed files: $FAILED**"; } >> "$GITHUB_STEP_SUMMARY"
fi
[ $FAILED -eq 0 ]
