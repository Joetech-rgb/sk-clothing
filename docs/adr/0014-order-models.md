# ADR 0014: Order models and the transition service

Status: proposed. Items marked CONFIRM are my reading where the brief is silent.

## What this change is
The database side of orders: `Order`, `OrderLine`, `OrderEvent` and `SubOrder`, and two services:
`create_order()` and `transition()`. It wraps the pure state machine from ADR 0010 and does not
change any rule in it. There is no cart, no checkout and no payment code here. Those are the next
two changes.

## Decisions
- **Status fields change only through `services.transition()`.** It locks the order row, applies
  the event with `apply_event`, saves, and writes one `OrderEvent`. A repeated event is a no-op and
  writes nothing. An illegal event raises and changes nothing. If a transition would break an
  invariant, it is rolled back and raised as `InconsistentState`.
- **Lines and events are append-only.** Saving over, updating or deleting them raises
  `ImmutableError`. Orders cannot be deleted; they are cancelled.
- **Other apps are referenced by plain integer ids** (`variant_id`, `vendor_id`), not foreign keys,
  so `import-linter` stays green and history survives catalog edits. The customer is a nullable
  foreign key, because guest checkout is in scope.
- **The database enforces** a unique idempotency key, a unique reference, non-negative amounts,
  quantity of at least 1, and `line_total = unit_price x quantity`.
- **Lines carry** variant id, name as shown, quantity, tier used, unit price, line total, list
  price, tier price, price source and the applied-discount detail. Batch cost, dividend reserve and
  commission are not here yet; they arrive with Phases 3 and 4 as expand-only migrations.
- **`SubOrder`**: one per order, `vendor_id` null (section 6 of the brief).
- **Admin is read-only.** Staff will act through services, not by editing status fields.

## Interpretations (CONFIRM)
1. The delivery fee is null while an order awaits a quote, and the total is undefined until then.
2. Creation is recorded as an `OrderEvent` named `created`, with no "before" state.
3. Pickup orders must be created with a fee of 0 (the brief says pickup is free).
4. Setting the staff quote (the fee amount) is not built here. `quote_set` moves the state, but the
   service that stores the fee comes with the staff quote screen.

## How it was checked
34 tests against a real database schema built from the migration, plus a mutation check: seven
deliberate breakages (no replay guard, no invariant check, wrong event name, editable lines, a weakened
line-total rule, missing pickup-fee rule) were each caught. One mutation (removing the early
duplicate-key lookup) is harmless because the database check gives the same result.

Not yet verified: any run on PostgreSQL, and two buyers racing on `transition()` (SQLite ignores
row locks). The first CI run covers the first; the second needs a concurrency test on Postgres.
