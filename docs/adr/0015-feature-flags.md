# ADR 0015: Feature flags with an audit trail

Status: accepted. The three CONFIRM items were confirmed by the client developer on 2026-10-27.

## What this change is
A database-backed switch table so unfinished features can ship turned off and `main` always
deploys (CLAUDE.md section 4). Staff flip a flag in the admin without a deploy, and every change is
recorded: who, what and when.

## Decisions
- **A separate `flags` app**, approved by the client's developer. It keeps `analytics` free.
- **A flag that does not exist is off.** New code can ship dark.
- **Keys are lower-case slugs** (letters, digits, underscores, start with a letter, 2 to 64
  characters), checked on every save.
- **`services.set_flag(key, enabled, actor=..., description=None)` is the only write path.** It
  locks the row, saves, and writes one `FlagChange` in the same transaction. Setting the value a
  flag already has records nothing. Saving the model directly, `objects.create`, `bulk_create`,
  `update` and `delete` all raise `DirectWriteError`, so the history cannot be skipped.
- **History is append-only.** `FlagChange` rows cannot be edited or deleted through the ORM.
  Flags are never deleted; they are switched off. Raw SQL and data migrations can still bypass
  these guards, which is accepted: the database user for the app should not be used for that.
- **The actor is a plain string** (`user:12`, `system`), not a foreign key, so history survives
  user deletion and this app depends on no other app. The admin sets it from the logged-in user.
- **No cache, deliberately.** A flag is also a kill switch, so switching it off must apply to the
  next request. A time-delayed cache would break that. The checks are cheap instead:
  - `is_enabled(key)`: one indexed query.
  - `snapshot()`: one query loads every flag that is on; any number of checks after that cost zero
    queries. Build one per request or task. It is never shared between requests.
- If profiling later shows flag reads matter, add a Redis cache that `set_flag` clears on write.

## Interpretations (CONFIRMED)
1. Any staff user with the Django permission to change flags may flip one. There is no separate
   role.
2. The admin shows history read-only on its own screen. A flag cannot be renamed after creation.
3. Seeding flags from a data migration is not covered; use `set_flag(..., actor="system")`.

## How it was checked
38 tests, plus a mutation check: 14 deliberate breakages (ignoring the on switch, recording
no-ops, no audit row, wrong before value, wrong actor, optional actor, no race retry, snapshot
querying the database, direct saves allowed, bulk update allowed, editable history, no key
validation, admin skipping the audit, admin delete allowed) were each caught. Query counts are
asserted. Not yet run on PostgreSQL.

## Not built yet
Per-user or percentage rollouts, a cache, and an API endpoint for the storefront to read flags.
