# ADR 0011: Foundation layer (user model, API errors, request IDs, health)

Status: proposed.

## Decisions
1. **Custom user model `identity.User`, chosen now.** `AUTH_USER_MODEL` cannot be changed cheaply
   once a real database exists. Email and phone are both optional, at least one is required
   (a database check), each is unique when present. Email is stored lower case; phone is stored as
   E.164 whoever creates the user. Customers use a login code, email or Google; staff use email
   and password. Staff two-factor (TOTP) is required by the brief and is **not** built here: it
   needs a library choice (django-otp or similar) and approval.
2. **Secure by default.** Every API view is private unless it explicitly opens itself. Basic
   authentication is removed (it sends the password on every request). Sessions only, and an
   anonymous caller gets **401** so the storefront can show a login screen.
3. **One error envelope** for every error, including 404 and 500:
   `{"error": {"code", "message", "details"?, "request_id"?}}`. Codes are stable strings.
4. **Request IDs.** Every response carries `X-Request-ID`; the same ID is in every log line and in
   Sentry. A caller's ID is kept only if it is a plain token (8 to 64 safe characters).
5. **Phone numbers never reach the logs.** A logging filter masks any phone-shaped text to its last
   three digits, as a second line of defence behind "never log one".
6. **Real client address behind Cloudflare.** Per-IP limits need the caller's real address.
   `CF-Connecting-IP` is believed only when `TRUST_CLOUDFLARE_HEADERS=1`. **That must only be set
   once the server accepts traffic from Cloudflare alone** (firewall rule), otherwise anyone can
   invent an address and dodge every limit. Default limits are 300 a minute for anonymous callers
   and 600 for logged-in users: deliberately generous because many Ghanaian phones share one carrier
   address. Login and payment endpoints will get tighter limits of their own (CONFIRM the numbers).
7. **Separate caches.** Throttle counters use a Redis cache that is separate from the Celery broker
   (`CACHE_URL` vs `REDIS_URL`): a broker must never evict queued tasks. Local and CI use an
   in-memory cache.
8. **Two health endpoints.** `/api/v1/health/` is liveness (cheap). `/api/v1/health/ready/` checks
   the database and Redis and answers 503 if either is down, without leaking details. The uptime
   monitor should watch the second.
9. **Password rules** (length, common passwords, similarity, numeric-only) are on for staff
   accounts.

## Migrations that cannot be run here
The user-model migration is hand-written and must match Django's own output exactly. A workflow
(`generate-migrations.yml`) lets GitHub write migrations itself: put `[gen-migrations]` in a commit
message and push; it runs `makemigrations` and commits the result. Because no database has been
deployed yet, the initial migrations can still be regenerated cleanly before the first staging
deploy.

## Not built yet
Throttles specific to login-code requests (per number, per IP, the daily SMS spend cap), the
login-code endpoints, Google sign-in, staff two-factor, and the security headers for production.
