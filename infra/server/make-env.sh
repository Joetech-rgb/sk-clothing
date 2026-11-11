#!/usr/bin/env bash
# Writes the server's .env with fresh random secrets. Run once, from the repository folder:
#   bash infra/server/make-env.sh staging.example.com you@example.com
# It refuses to overwrite an existing .env. It prints the /admin/ gate password ONCE: save it.
# Afterwards edit .env by hand to add the Paystack key and the (public) Mapbox token.
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
OUT="${OUT:-.env}"
if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "usage: bash infra/server/make-env.sh <domain> <email-for-certificate-notices>" >&2
  exit 2
fi
if ! [[ "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; then
  echo "that does not look like a domain name: $DOMAIN" >&2
  exit 2
fi
if ! [[ "$EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  echo "that does not look like an email address: $EMAIL" >&2
  exit 2
fi
if [ -e "$OUT" ]; then
  echo "$OUT already exists. Not overwriting it." >&2
  exit 1
fi

rand() { head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-"$1"; }

hash_password() {
  if [ -n "${CADDY_BIN:-}" ]; then
    "$CADDY_BIN" hash-password --plaintext "$1"
  else
    docker run --rm caddy:2 caddy hash-password --plaintext "$1"
  fi
}

gate_password="$(rand 20)"
gate_hash="$(hash_password "$gate_password")"

umask 077
cat > "$OUT" <<ENVEOF
# Written by infra/server/make-env.sh. Secrets live ONLY here. Never commit this file.
# Which parts of the stack start: Caddy (HTTPS without Cloudflare) and the storefront.
COMPOSE_PROFILES=caddy,storefront

DJANGO_SETTINGS_MODULE=config.settings.staging
DJANGO_SECRET_KEY=$(rand 64)
ALLOWED_HOSTS=$DOMAIN
# The storefront's own address. Login, checkout and payment calls are refused from any other origin.
CSRF_TRUSTED_ORIGINS=https://$DOMAIN

POSTGRES_DB=skclothing
POSTGRES_USER=sk
POSTGRES_PASSWORD=$(rand 32)
POSTGRES_HOST=db
# The broker and the cache are different Redis servers on purpose (ADR 0009).
REDIS_URL=redis://redis-broker:6379/0
CACHE_URL=redis://redis-cache:6379/0
LOG_LEVEL=INFO

# 1 is safe here: Caddy overwrites CF-Connecting-IP with the address it really saw, and Django is
# not reachable except through Caddy. It makes per-visitor limits work instead of treating
# everyone as one visitor.
TRUST_CLOUDFLARE_HEADERS=1

# Fill these in when you have them.
PAYSTACK_SECRET_KEY=
SENTRY_DSN=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
# PUBLIC Mapbox token only (starts with pk.). Baked into the storefront when its image is built.
NEXT_PUBLIC_MAPBOX_TOKEN=

GUNICORN_WORKERS=3
GUNICORN_THREADS=2

# The web edge (Caddy).
SITE_ADDRESS=$DOMAIN
ACME_EMAIL=$EMAIL
ADMIN_BASIC_USER=gate
# Single quotes keep the dollar signs in the hash literal.
ADMIN_BASIC_HASH='$gate_hash'
ENVEOF

echo "Wrote $OUT"
echo
echo "The /admin/ gate (a password prompt in front of Django's own login):"
echo "  user:     gate"
echo "  password: $gate_password"
echo "Save that password now. It is not stored anywhere else, only its hash is."
