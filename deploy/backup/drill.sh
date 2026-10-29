#!/usr/bin/env bash
# SPNC restore drill (docs/44 §3.5, D6). Proves that a backup set restores into an empty stack.
#
#   deploy/backup/drill.sh
#
# Uses its own compose project, ports, volumes and backup directory; never the demo stack.
# Environment:
#   DRILL_PROJECT             compose project (default spnc-drill)
#   DRILL_API_PORT            API host port (default 8018)
#   DRILL_MINIO_CONSOLE_PORT  MinIO console host port (default 9018)
#   PYTHON                    Python with apps/api/requirements.txt installed (default python)
#   DRILL_KEEP=1              leave the stack and .drill/<project> in place for inspection
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: keep container paths such as /backups as they are

PROJECT="${DRILL_PROJECT:-spnc-drill}"
API_PORT="${DRILL_API_PORT:-8018}"
CONSOLE_PORT="${DRILL_MINIO_CONSOLE_PORT:-9018}"
PYTHON="${PYTHON:-python}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

case "$PROJECT" in
  phase11|spnc|"$(basename "$ROOT")") echo "Refusing to run the drill on compose project '$PROJECT'" >&2; exit 2 ;;
esac

WORK=".drill/$PROJECT"              # relative to the compose file, so it works on any host OS
rm -rf "$WORK"
mkdir -p "$WORK/backups"
r() { "$PYTHON" -c "import secrets; print(secrets.token_hex(16))"; }
POSTGRES_PASSWORD="$(r)"
ADMIN_PASSWORD="$(r)"
cat > "$WORK/.env" <<EOF
POSTGRES_USER=spnc
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=spnc
MINIO_ROOT_USER=spnc-minio
MINIO_ROOT_PASSWORD=$(r)
S3_BUCKET=spnc-snapshots
SECRET_KEY=$(r)$(r)
SPNC_BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PASSWORD
API_PORT=$API_PORT
MINIO_CONSOLE_PORT=$CONSOLE_PORT
BACKUP_DIR=./$WORK/backups
EOF

dc() { docker compose -p "$PROJECT" --env-file "$WORK/.env" "$@"; }
teardown() {
  if [ "${DRILL_KEEP:-0}" = "1" ]; then
    echo "DRILL_KEEP=1: stack '$PROJECT' and $WORK left in place"
  else
    # Sets are written by root with mode 0700 (Linux hosts): remove them from inside the container
    dc run --rm --no-deps --entrypoint sh backup -c 'rm -rf /backups/* /backups/.[!.]*' > /dev/null 2>&1 || true
    dc down -v --remove-orphans > /dev/null 2>&1 || true
    rm -rf "$WORK"
  fi
}
trap teardown EXIT

wait_api() {
  for _ in $(seq 1 90); do
    curl -fs "http://127.0.0.1:$API_PORT/docs" > /dev/null && return 0
    sleep 2
  done
  echo "API did not come up" >&2
  dc ps
  dc logs --tail 100 api migrate
  return 1
}

e2e() {
  ( cd apps/api && SPNC_E2E_BASE_URL="http://127.0.0.1:$API_PORT" SPNC_E2E_ADMIN_USER=admin \
      SPNC_E2E_ADMIN_PASSWORD="$ADMIN_PASSWORD" SPNC_E2E_ADMIN_NEW_PASSWORD="Drill-$POSTGRES_PASSWORD" \
      SPNC_DRILL_STATE="../../$WORK/state.json" DATABASE_URL=postgresql://unused:unused@localhost/unused \
      "$PYTHON" -m pytest "$@" -q -p no:warnings )
}

step() { echo; echo "== [$(date -u +%H:%M:%S)] $*"; }

step "1/6 Start stack '$PROJECT' and seed data"
dc up -d --build
wait_api
dc exec -T api python -m app.cli create-admin --username admin --email admin@example.org
e2e tests/e2e/test_compose_stack.py
SPNC_DRILL_PHASE=seed e2e tests/e2e/test_backup_drill.py

step "2/6 Backup"
dc run --rm --no-deps backup backup
SET="$(dc run --rm --no-deps backup list | tr -d '\r' | tail -1)"
[ -n "$SET" ] || { echo "No backup set was created" >&2; exit 1; }
dc run --rm --no-deps backup verify-set "$SET"
echo "Set: $SET"
dc run --rm --no-deps --entrypoint cat backup "/backups/$SET/manifest.json" | "$PYTHON" -c "import json,sys; m=json.load(sys.stdin); print('rows', sum(m['row_counts'].values()), 'tables', len(m['row_counts']), 'blobs', len(m['blobs']), 'revision', m['alembic_revision'])"

step "3/6 Destroy the stack and all its volumes"
dc down -v
[ -z "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT")" ] || { echo "volumes survived" >&2; exit 1; }

step "4/6 Restore into an empty stack"
T0=$(date +%s)
dc up -d postgres minio-init minio
dc run --rm --no-deps backup restore "$SET"

step "5/6 Start the full stack on the restored data"
dc up -d
wait_api
dc run --rm --no-deps backup verify-live
SPNC_DRILL_PHASE=check e2e tests/e2e/test_backup_drill.py
e2e tests/e2e/test_compose_stack.py
T1=$(date +%s)

step "6/6 Result"
echo "RESTORE DRILL PASSED: set $SET restored and verified in $((T1 - T0)) s (RTO 4 h = 14400 s)"
