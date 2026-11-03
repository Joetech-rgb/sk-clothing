#!/usr/bin/env bash
# Restore drill. Restores a backup into a throw-away database, checks it, and records the result.
#
#   bash infra/backup/restore.sh /var/backups/skclothing/daily/skclothing-<stamp>.dump [--keep]
#
# It NEVER touches the live database: it creates restore_drill_<stamp>, loads the dump there, and
# drops it again (unless --keep). The result and the time taken are appended to $BACKUP_DIR/drill.log.
# A real disaster restore is a manual, supervised procedure: see docs/runbooks/OPERATIONS.md.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/skclothing}"
VERIFY_TABLES="${VERIFY_TABLES:-identity_user orders_order payments_paymentattempt}"

dc() { docker compose -f "$COMPOSE_FILE" "$@"; }

FILE="${1:-}"
KEEP=0
[ "${2:-}" = "--keep" ] && KEEP=1
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "usage: bash infra/backup/restore.sh <dump-file> [--keep]" >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
log_result() { # log_result <text>: one line per drill in $BACKUP_DIR/drill.log
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) file=$(basename "$FILE") $1" >> "$BACKUP_DIR/drill.log"
}

if [ -f "$FILE.sha256" ]; then
  if ! (cd "$(dirname "$FILE")" && sha256sum -c "$(basename "$FILE").sha256"); then
    log_result "result=FAIL reason=checksum_mismatch"
    echo "RESTORE DRILL FAILED: checksum does not match" >&2
    exit 1
  fi
else
  echo "WARNING: no checksum file next to the dump, so its integrity is not proven" >&2
fi

scratch="restore_drill_$(date -u +%Y%m%d%H%M%S)"
cleanup() {
  if [ "$KEEP" -eq 0 ]; then
    # shellcheck disable=SC2016
    dc exec -T "$DB_SERVICE" sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$1"' _ "$scratch" \
      >/dev/null 2>&1 || true
  else
    echo "Kept scratch database: $scratch (drop it yourself when done)"
  fi
}
trap cleanup EXIT

start=$SECONDS
echo "Creating scratch database $scratch"
# shellcheck disable=SC2016  # single quotes on purpose: the container's own shell expands these
if ! dc exec -T "$DB_SERVICE" sh -c 'createdb -U "$POSTGRES_USER" "$1"' _ "$scratch"; then
  log_result "result=FAIL reason=could_not_create_scratch_database"
  echo "RESTORE DRILL FAILED: could not create the scratch database" >&2
  exit 1
fi
echo "Restoring $(basename "$FILE")"
# shellcheck disable=SC2016
if ! dc exec -T "$DB_SERVICE" sh -c 'pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error' \
  _ "$scratch" < "$FILE"; then
  log_result "result=FAIL reason=pg_restore_error restore_seconds=$(( SECONDS - start ))"
  echo "RESTORE DRILL FAILED: the dump could not be restored" >&2
  exit 1
fi
elapsed=$(( SECONDS - start ))

psql_scratch() { # psql_scratch <sql>
  # shellcheck disable=SC2016
  dc exec -T "$DB_SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d "$1" -At -c "$2"' _ "$scratch" "$1"
}

ok=1
tables="$(psql_scratch "select count(*) from information_schema.tables where table_schema='public'")"
echo "Restored in ${elapsed}s. Tables in the public schema: $tables"
[ "${tables:-0}" -gt 0 ] || ok=0
for t in $VERIFY_TABLES; do
  if ! [[ "$t" =~ ^[a-z_][a-z0-9_]*$ ]]; then echo "  skipping odd table name: $t"; ok=0; continue; fi
  if n="$(psql_scratch "select count(*) from $t" 2>/dev/null)"; then
    echo "  $t: $n rows"
  else
    echo "  $t: MISSING"; ok=0
  fi
done

result=PASS; [ "$ok" -eq 1 ] || result=FAIL
log_result "restore_seconds=$elapsed public_tables=$tables result=$result"
echo "RESTORE DRILL RESULT: $result (logged to $BACKUP_DIR/drill.log)"
[ "$ok" -eq 1 ] || exit 1
