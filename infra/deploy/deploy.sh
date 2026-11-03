#!/usr/bin/env bash
# Deploy the backend on the server. The "Deploy staging" workflow checks out the commit and then runs
# this. By hand:   HEALTH_URL=https://staging.example.com/<health path> bash infra/deploy/deploy.sh <sha>
#
# Order: backup, build, start the database, migrate, start everything, wait for a healthy answer.
# If anything fails it puts the previous version back. Migrations are not undone: they are
# expand-then-contract (CLAUDE.md section 4), so the previous code still works on the new schema.
set -euo pipefail

SHA="${1:?usage: deploy.sh <git-sha>}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
APP_SERVICE="${APP_SERVICE:-backend}"
HEALTH_URL="${HEALTH_URL:?set HEALTH_URL to the readiness check address}"
PRE_DEPLOY_BACKUP="${PRE_DEPLOY_BACKUP:-1}"
HEALTH_TRIES="${HEALTH_TRIES:-30}"   # how many checks, HEALTH_WAIT seconds apart
HEALTH_WAIT="${HEALTH_WAIT:-5}"
STATE_FILE="${STATE_FILE:-$HOME/.skclothing_last_deployed_sha}"

dc() { docker compose -f "$COMPOSE_FILE" "$@"; }

current="$(git rev-parse HEAD)"
if [ "$current" != "$SHA" ]; then
  echo "The checked-out commit ($current) is not the one to deploy ($SHA)" >&2
  exit 1
fi
previous="$(cat "$STATE_FILE" 2>/dev/null || true)"

health() {
  for _ in $(seq 1 "$HEALTH_TRIES"); do
    if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then return 0; fi
    sleep "$HEALTH_WAIT"
  done
  return 1
}

rollback() {
  echo "DEPLOY FAILED." >&2
  if [ -n "$previous" ]; then
    echo "Putting back $previous" >&2
    git checkout --detach "$previous"
    dc up -d --build
    if health; then echo "Previous version is healthy again." >&2
    else echo "THE PREVIOUS VERSION IS ALSO UNHEALTHY. A person must look at this now." >&2; fi
  fi
  exit 1
}

if [ "$PRE_DEPLOY_BACKUP" = "1" ]; then bash infra/backup/backup.sh; fi

dc build || rollback
dc up -d "$DB_SERVICE" || rollback
dc run --rm -T "$APP_SERVICE" python manage.py migrate --noinput || rollback
dc up -d || rollback
health || rollback

echo "$SHA" > "$STATE_FILE"
echo "Deployed $SHA"
