# Proposal 0001: production application server and routing

Status: **proposal, the human decides.** Author: Agent A. Date: 4 November 2026.
Answers open question 12 (production web server) and Agent C's request 4 (how `/api/v1` is routed).

I have not seen `docker-compose.yml`, `infra/Dockerfile.backend` or `backend/requirements/*.txt` yet. Anything marked **[CHECK]** is an assumption to confirm against them before building.

## What I know from the repository

- Django 5 with Django REST Framework, behind Cloudflare, then a reverse proxy, on one VPS using Docker Compose (`CLAUDE.md` sections 2 and 3). Nginx is already named in the planned layout (`infra/`).
- The backend expects a proxy in front of it: `SECURE_PROXY_SSL_HEADER` is set in staging and production, and `TRUST_CLOUDFLARE_HEADERS` exists for the real client address (`base.py`, ADR 0002).
- The code is synchronous and relies on database row locks inside transactions (stock reservation, checkout, payment confirmation). Concurrency tests prove this behaviour today.
- Static files are collected into `STATIC_ROOT` (`BASE_DIR / "staticfiles"`), so something must serve them.
- Celery workers and beat run as separate processes. Realtime chat with Django Channels is Phase 2.

## The choice

| Option | What it is | For | Against |
|---|---|---|---|
| **A. Gunicorn, threaded sync workers** | The standard WSGI server | Matches how all current code and tests behave. Well understood. Smallest risk before 13 November | No websockets, so Phase 2 needs a second process |
| B. ASGI from day one (Uvicorn) | One async-capable server | One model for HTTP and websockets later | Sync views run in a thread pool: behaviour of our locks and transactions would need re-testing. More moving parts now |
| C. Daphne | The Channels reference server | Channels-native | Same re-testing cost as B, and a smaller ecosystem for production tuning |

## Recommendation

**Option A for launch.** Run Gunicorn behind Nginx. In Phase 2, add a separate ASGI process (Uvicorn or Daphne) for websockets only, and let Nginx send `/ws/` to it. HTTP keeps running on the tested sync path. This moves no risk into the weeks before hand-over.

New dependency: **`gunicorn`**, production use only. Cost: none (open source). Memory: roughly one Django process per worker; the worker count depends on the VPS size (open question 10). Maintenance: keep it patched with the rest of the requirements. No other new dependency is needed.

## Routing (answers Agent C's request 4)

Route at Nginx, not through the Next.js app:

- `/api/` and `/admin/` go to Django (Gunicorn).
- `/static/` is served by Nginx from the collected static folder.
- Everything else goes to the Next.js server.
- Next.js's `rewrites` stay for local development only.

Why: a rewrite makes every API call, including checkout, pass through Next.js first, which adds a hop and ties API availability to the Next.js process. Django's rate limiting needs the real client address, which arrives through Cloudflare and Nginx headers; adding Next.js in the middle puts that chain at risk. Cookies, CSRF and the Origin check work the same either way, because both are same-origin.

Set `TRUST_CLOUDFLARE_HEADERS=1` only when the server accepts traffic from Cloudflare alone (firewall rule on the VPS), as `base.py` already says.

## What gets built if approved

1. `gunicorn` added to the production requirements. **[CHECK]** the requirements layout, so CI installs stay the same.
2. A production Compose file with: `backend` (Gunicorn), `worker` and `beat` (Celery), `db`, `redis`, `web` (Next.js), `nginx`. **[CHECK]** service names against the current `docker-compose.yml`. The deploy workflow defaults to `backend` and `db`.
3. An Nginx configuration with the routing above, security headers, and the Cloudflare real-IP handling.
4. A health endpoint check wired into the deploy script and the uptime monitor (the readiness endpoint exists, ADR 0011).
5. A note for Agent C: the Next.js app needs a standalone production build (`output: "standalone"`) so it can run as a small container. **[CHECK]** with Agent C.

## Decisions I need from the human

1. Approve `gunicorn` as the only new dependency, or choose option B or C.
2. Approve routing at Nginx (above), so Agent C can finish its request.
3. VPS size: processors, memory, disk (open question 10). It sets the worker count.
4. TLS: a Cloudflare origin certificate or Let's Encrypt. I would use the Cloudflare origin certificate with SSL mode "Full (strict)".

## Not decided here

Backups and the restore drill (see `docs/runbooks/OPERATIONS.md`), the monitoring accounts, and the staging server's hostname.
