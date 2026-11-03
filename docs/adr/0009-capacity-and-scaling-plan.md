# ADR 0009: Capacity targets, load testing, monitoring, backups and upgrade path

Status: proposed. Numbers below marked ESTIMATE are my arithmetic, not measurements. They are
replaced by measurements from the load tests.

## Targets (CONFIRM which is the pass mark)
The client gave two sets of numbers. I read them as two tiers and will test both.

| | Launch planning target | Stretch target |
|---|---|---|
| Concurrent visitors | 100 | 500 |
| Products | 5,000 | 10,000 |
| Peak orders per hour | 30 | 60 |

These are test targets, not promised capacity. Capacity is established by load and stress
testing on a production-equivalent environment. The plan is a Hostinger KVM 2 (2 vCPU, 8 GB RAM,
100 GB NVMe, 8 TB bandwidth) first, changed only if measurements say so.

## What the numbers mean (ESTIMATE)
Assume a visitor loads a page about every 15 seconds. 100 visitors is about 7 page views a second;
500 is about 33. With 2 to 4 uncached API calls per view and a 2 to 3 times peak factor, the origin
could see roughly 40 to 60 requests a second at the launch tier and 200 to 300 at the stretch tier,
before Cloudflare caching removes a share. Orders are tiny by comparison: 30 an hour is one every
two minutes, 60 an hour is one a minute. Checkout is a correctness problem (overselling, duplicate
callbacks), not a volume problem. **Browsing and search on 2 vCPUs are the real risk**, because
Django, PostgreSQL, Redis, Celery and Next.js all share the same two cores.

## Memory budget on 8 GB (ESTIMATE, to be replaced by `docker stats`)
OS and Docker 0.7 GB; PostgreSQL about 2.1 GB (1.5 GB shared buffers plus connections); two Redis
instances 0.3 GB; Django (3 workers) 0.6 GB; Celery default 0.4 GB; Celery media 0.5 GB (measured
about 200 MB per photo at the 50 MP cap, ADR 0005); Celery beat 0.1 GB; Next.js 0.5 GB; Nginx and
agents 0.15 GB. About 5.4 GB, leaving about 2.6 GB for the database file cache. CPU is the scarce
resource, not memory.

## Rules that protect the 2 vCPU box
- Docker resource limits on every container, with the media worker at a low CPU share so photo
  jobs can never slow checkout or webhooks. Image jobs run on their own `media` queue.
- **Two Redis instances:** the Celery broker must never evict keys (`noeviction`); the cache should
  (`allkeys-lru`). One shared instance can lose queued tasks under memory pressure.
- Cloudflare caches images and static files (immutable URLs) and short-TTL public catalog pages and
  JSON with stale-while-revalidate. Next.js pre-renders catalog pages where possible.
- Persistent database connections and a capped number of workers, so connections stay well under
  `max_connections`. PgBouncer only if measurements need it.
- `pg_stat_statements` on, slow-query log on, no N+1 on any list endpoint (a test already guards
  `price_cart`).

## Load tests (before production launch)
Run from a separate machine, never from the VPS itself, against a staging copy sized like
production with 10,000 seeded products, variants, tiers and stock. Proposed tool: **k6** (one
binary, scripted in JavaScript; new tooling, needs approval). Scenarios: product browsing, search,
cart operations, concurrent checkouts, stock reservation and contention on one popular item,
Paystack webhook processing including replays, background jobs under load (including a photo
batch), and database performance. Also a spike test (3 times the launch tier) and a 2-hour soak.

Measure: response time (p50, p95, p99) per endpoint, error rate, CPU and memory per container,
database connections and lock waits, queue depth, and checkout success.

Proposed pass marks (CONFIRM): browse p95 under 500 ms on cache hits and under 1.5 s on misses;
search p95 under 800 ms; checkout creation p95 under 1.5 s; error rate under 1%; **zero oversells
and zero double payments in the contention and replay tests**; sustained CPU under 70% at the launch
tier and under 85% at the stretch tier; no swap use; database connections under 70% of the limit.

## Monitoring (each service needs approval; all have free tiers)
Sentry for errors and slow traces; an uptime monitor on a health endpoint that also checks the
database and Redis (today's `/api/v1/health/` does not, so a second "readiness" endpoint is needed);
host and container metrics (Netdata is the lightest to start; Prometheus and Grafana if needed
later); Cloudflare analytics. Alerts: disk over 80%, memory over 85%, CPU over 85% for 10 minutes,
queue depth growing, failed background tasks, webhook failures, a refund unresolved after 24 hours,
backup older than 26 hours, restore drill overdue.

## Backups and recovery
Nightly full database dump plus continuous archiving of the write-ahead log to Cloudflare R2 for
point-in-time recovery, encrypted, with the key stored away from the server. Proposed objectives
(CONFIRM): at most 15 minutes of data lost, back in service within 4 hours. A restore test runs
automatically every week into a scratch container and passes only if row counts and the stock
ledger consistency check pass; a full rebuild on a fresh VPS is rehearsed before launch and every
quarter. A backup that has not been restored is not counted. I have not verified what backup or
snapshot features the Hostinger plan includes, so they are an extra layer, never the plan.

## Upgrade path, with triggers
0. Tune: indexes, query counts, caching, pre-rendering. Trigger: a pass mark missed.
1. Bigger single server (more vCPU and RAM). Trigger: CPU over 70% at peak after tuning.
2. Database on its own server or a managed PostgreSQL. Trigger: database CPU or disk contention,
   or a need for automatic failover.
3. Several web servers behind Cloudflare load balancing, workers on their own server. Trigger:
   one server is saturated or one machine is too risky a single point of failure.
4. Read replica for catalog and search reads, Meilisearch on its own server (Phase 1B).
5. Managed Redis and queue, high availability across servers.

## Design rules kept now so every step stays possible
Stateless web containers; no files on local disk (photos and backups are in R2); all configuration
and hostnames from the environment; background jobs idempotent; sessions server-side, not on the
web server; no app imports another app's models (import-linter, so a module can be split out);
unfinished features behind database flags.

## Honest limits
A single VPS is a single point of failure, and "more than a million users" cannot be promised from
it. It is plausible as registered users over time because most browsing is served from Cloudflare's
cache, but only the load test and later monitoring can say what this server really carries.
