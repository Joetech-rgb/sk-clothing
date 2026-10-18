# ADR 0006: Stock ledger, FIFO batches and reservations

Status: proposed

## Decision
New `inventory` app (approved by the client in conversation). Stock for a variant is the sum of
append-only `StockMovement` rows. `StockLevel` (totals) and `Batch.quantity_remaining` are caches
written in the same transaction as the movement.

- **Functional core, imperative shell.** `allocation.py` (FIFO choice and the ledger consistency
  rules) is pure Python with exhaustive tests. `services.py` locks rows and writes.
- **Locking.** Every change locks the variant's `StockLevel` row first (`select_for_update` inside
  `transaction.atomic`). Anything touching several variants locks them in ascending `variant_id`
  order, so opposite-order carts cannot deadlock. Two buyers on the last unit: exactly one wins.
- **Reservations** expire after 15 minutes. `expire_reservations` runs every minute (Celery Beat).
  `reserve_many` is all-or-nothing for a cart.
- **Sales** (`confirm_sale`) take the oldest batch first by `received_at`, then id, so a backdated
  receipt is correctly treated as older.
- **Idempotency.** Receipts, reservations and confirmations are safe to repeat. A key reused for a
  different request raises `IdempotencyConflict`.
- **Database guards.** Negative stock, more held than on hand, zero-quantity movements, and any
  UPDATE or DELETE on movements (a Postgres trigger) are refused by the database itself.
- **`variant_id` is a plain integer, not a foreign key.** Apps never import each other's models
  (CLAUDE.md section 4). Trade-off: no database-level proof the variant exists, so callers must
  check with the catalog service before receiving stock.
- **`Batch.unit_cost_pesewas` is nullable.** Costing is Phase 3. Order lines freeze batch cost
  later, so the column exists now and is filled when costing arrives.
- **Admin is read-only** for every inventory table: "watch stock", never edit a number.

## Not built (later phases)
Adjustments and stocktake, damaged-goods states, returns routing, barcodes, low-stock alerts,
clearance flags (Phase 2). Cost allocation (Phase 3). A screen to receive stock: until then stock
arrives through the service (the bulk import in Phase 1A will call it).

## Open business question (do not guess)
If a customer's payment is confirmed **after** their 15-minute hold expired, what should happen?
`confirm_sale` raises `ReservationNotActive` and changes nothing. Options for the orders layer:
(a) re-reserve if stock is still free, otherwise refund automatically; (b) always refund
automatically; (c) put the order in an admin queue. Recommendation: (a), with the refund going to
the original payment method. Needs the client's answer before orders are built.

## Scalability notes
- A very popular single variant serialises on one row lock. That is correct for avoiding
  oversell, and at a few milliseconds per reservation it handles hundreds of reservations a
  second per variant. A flash sale on one item would need a different design (not planned).
- `available()` reads Postgres. Storefront "stock left" will be read far more than written, so it
  should be cached with a short TTL once traffic justifies it. The cache may be slightly stale;
  the reservation is always the authority.
- No row locks are held across a payment. A hold is a row, not an open transaction.
- Row-lock waits surface as slow requests. Set a database `lock_timeout` when orders are built.

## Verification status
Pure core: 14 tests plus a 200-history random simulation, mutation-tested here. The database layer
and its tests (including the concurrency tests with real threads) have not run anywhere yet; the
first CI run is their first execution.
