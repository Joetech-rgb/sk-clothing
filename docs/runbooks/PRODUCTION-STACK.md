# Production stack (DRAFT, needs proposal 0001 approved)

Status date: 8 November 2026. Owner: Agent A. Replaces nothing: local development keeps `docker-compose.yml`.

## Tested and not tested

| Part | Tested how |
|---|---|
| `infra/nginx/default.conf` | Run with real nginx 1.24 in front of a fake backend: http redirects to https; `/api/` and `/admin/` reach Django; `/static/` is served from disk; a forged `CF-Connecting-IP` from an untrusted source is overwritten; a trusted Cloudflare source gives the real client address; nginx stays up when the storefront is not running (502, no crash) |
| `infra/nginx/update-cloudflare-ips.sh` | Fake downloads: good lists are written; a garbage line, too few ranges and a failed download all write nothing. `shellcheck` clean |
| `docker-compose.prod.yml` | YAML parses; service names match the deploy workflow (`backend`, `db`). **Never run with Docker** |
| `infra/Dockerfile.backend.prod`, `backend/requirements/prod.txt` | **Never built** |
| `infra/Dockerfile.storefront` | Its steps were run for real on the current `main` outside Docker: install with the pinned pnpm, build with `NEXT_OUTPUT=standalone`, then start `server.js` from a clean folder containing only what the image copies. `/`, `/products`, `/cart`, `/checkout` and `/orders` answered 200, a built asset was served, `x-powered-by` was off, and the server used about 92 MB. **The Dockerfile itself was never built** |

Open items marked [CHECK]: `config/wsgi.py` exists; the chosen `DJANGO_SETTINGS_MODULE`.

## Changes from the local setup
- Django service is `backend` (the local file calls it `web`) and runs Gunicorn as a non-root user, not `runserver`.
- Two Redis servers: a broker that never drops tasks and a cache that may (ADR 0009). `REDIS_URL` and `CACHE_URL` in `.env` must point at `redis-broker` and `redis-cache`.
- nginx serves static files and routes `/api/` and `/admin/` to Django, everything else to the storefront.
- The database has a health check; the app waits for it.

## First start on the server
1. Create `.env` from `infra/production.env.example`. Fill in secrets on the server only.
2. In Cloudflare: SSL/TLS, Origin Server, create an origin certificate. Save the certificate as `infra/nginx/certs/origin.pem` and the key as `infra/nginx/certs/origin.key` (`chmod 600`). Set SSL mode to **Full (strict)**. Both files are git-ignored.
3. `bash infra/nginx/update-cloudflare-ips.sh`
4. Firewall: allow ports 80 and 443 only from Cloudflare's published addresses, and SSH only from your own address. Only then set `TRUST_CLOUDFLARE_HEADERS=1`.
5. `docker compose -f docker-compose.prod.yml up -d --build`
6. `docker compose -f docker-compose.prod.yml run --rm backend python manage.py migrate`
7. `docker compose -f docker-compose.prod.yml run --rm backend python manage.py createsuperuser`
8. Check the readiness address answers 200 through Cloudflare.

Staging deploy workflow settings: `STAGING_COMPOSE_FILE=docker-compose.prod.yml`. The defaults for the app and database service names already match.

## Later
- Start the storefront: `docker compose -f docker-compose.prod.yml --profile storefront up -d --build`. Put the PUBLIC Mapbox token in `.env` as `NEXT_PUBLIC_MAPBOX_TOKEN` first: it is baked in when the image is built, so rebuild after changing it.
- Add HSTS to nginx only after HTTPS has been proven on the domain.
- Rate limiting at nginx or Cloudflare is still provisional (ADR 0002).
- Re-run `update-cloudflare-ips.sh` about monthly, then reload nginx.
