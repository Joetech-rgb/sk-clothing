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
1. Any staff user holding the existing Django change permission may flip a flag. There is no
   separate role. Creating a flag needs the add permission. Nobody can delete a flag, whatever
   permissions they hold.
2. A flag's key cannot be renamed after creation. The admin shows it read-only.
3. Raw SQL and data migrations may bypass the guards. This limitation is accepted.

## How it was checked
48 tests, plus a mutation check: 22 deliberate breakages, each caught. They cover the audit trail
(no row, wrong before value, wrong actor, optional actor, recording no-ops, no race retry), the
write guards (direct save, bulk update, editable history), and permissions (key editable, any
staff may change, history editable, deletable or open to all staff, delete permission honoured).
Permission tests use real users: view-only staff, staff with no permissions, a customer holding
the permission, anonymous visitors, and a superuser. Query counts are asserted. The admin tests
use a copy of `identity.User` and its manager. Not yet run on PostgreSQL.

## Not built yet
Per-user or percentage rollouts, a cache, and an API endpoint for the storefront to read flags.
