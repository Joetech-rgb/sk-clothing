#!/usr/bin/env bash
# Database backup for the S.K Clothing platform.
#
# Run on the server, from the repository folder:   bash infra/backup/backup.sh
# Makes a compressed PostgreSQL dump, proves it can be read back, keeps a daily and a weekly copy,
# and removes old ones. It only ever reads the live database.
#
# A backup that exists only on the server it protects is not a backup. Set OFFSITE_COMMAND (see
# docs/runbooks/OPERATIONS.md) so every dump is also copied somewhere else.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/skclothing}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"

dc() { docker compose -f "$COMPOSE_FILE" "$@"; }

fail() {
  echo "BACKUP FAILED: $1" >&2
  if [ -n "${ON_FAILURE_COMMAND:-}" ]; then bash -c "$ON_FAILURE_COMMAND" || true; fi
  exit 1
}

umask 077
mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly" || fail "cannot create $BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
final="$BACKUP_DIR/daily/skclothing-$stamp.dump"
partial="$final.partial"
trap 'rm -f "$partial"' EXIT

echo "Backing up to $final"
# shellcheck disable=SC2016  # single quotes on purpose: the container's own shell expands these
dc exec -T "$DB_SERVICE" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' \
  > "$partial" || fail "pg_dump returned an error"
[ -s "$partial" ] || fail "the dump is empty"

# Prove the file is a readable dump that contains tables, before it is trusted.
entries="$(dc exec -T "$DB_SERVICE" pg_restore --list < "$partial" | grep -c 'TABLE ' || true)"
[ "${entries:-0}" -gt 0 ] || fail "the dump contains no tables"

mv "$partial" "$final"
(cd "$BACKUP_DIR/daily" && sha256sum "$(basename "$final")" > "$(basename "$final").sha256")
echo "Backup OK: $final ($(du -h "$final" | cut -f1), $entries table entries)"

# Sundays also keep a weekly copy.
if [ "$(date -u +%u)" = "7" ]; then
  cp -p "$final" "$final.sha256" "$BACKUP_DIR/weekly/"
fi

prune() { # prune <dir> <how many to keep>
  find "$1" -maxdepth 1 -name 'skclothing-*.dump' -printf '%T@ %p\n' \
    | sort -rn | tail -n +"$(( $2 + 1 ))" | cut -d' ' -f2- \
    | while IFS= read -r old; do rm -f -- "$old" "$old.sha256"; done
}
prune "$BACKUP_DIR/daily" "$KEEP_DAILY"
prune "$BACKUP_DIR/weekly" "$KEEP_WEEKLY"

if [ -n "${OFFSITE_COMMAND:-}" ]; then
  "$OFFSITE_COMMAND" "$final" "$final.sha256" || fail "the off-site copy failed"
  echo "Off-site copy OK"
else
  echo "WARNING: OFFSITE_COMMAND is not set. This backup exists only on this server." >&2
fi

if [ -n "${ON_SUCCESS_COMMAND:-}" ]; then bash -c "$ON_SUCCESS_COMMAND" || true; fi
