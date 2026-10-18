# ADR 0008: Late payment after reservation expiry, and refunds

Status: accepted policy from the client (2026-10-18); not built yet (needs the orders and
payments work in Phase 1A).

## Policy
When a payment is verified after the 15-minute stock hold has expired:
1. Try to reserve the stock again inside one atomic database transaction.
2. Stock available: allocate it and continue the order.
3. Stock not available: do not oversell. Start a refund to the original payment method and track
   it until confirmed.
4. Tell the customer the outcome.

Payment processing, stock allocation and refunds are idempotent. Payment, fulfilment and refund
status are three separate fields. Unresolved refunds have retry and manual resolution.

## Design
- **One transaction for re-reserve and sell.** `reserve_many` then `confirm_sale` inside a single
  `transaction.atomic()` (both already nest safely). If it raises `InsufficientStock` the whole
  transaction rolls back and nothing is held or sold.
- **Order of checks on a verified payment (webhook plus server-side verify):** de-duplicate by
  Paystack reference (done), confirm the amount equals the order total, then: hold still active ->
  confirm; hold expired or released -> re-reserve and confirm; no stock -> mark payment paid,
  fulfilment `not_fulfillable`, create the refund. Replaying the webhook any number of times gives
  the same result.
- **Statuses.** Payment: pending, paid, failed. Fulfilment: awaiting, reserved, allocated,
  not_fulfillable, then the delivery states. Refund: none, requested, submitted, processing,
  processed, failed, manual_resolution. None of them is derived from another.
- **Refund record.** One row per payment reference with a unique idempotency key
  (`refund:{payment_reference}`), amount in pesewas (the full amount here), Paystack's refund id,
  attempt count, last error, timestamps. A unique constraint means a double trigger cannot refund
  twice.
- **Tracking.** A Celery job submits the refund and polls or receives Paystack's refund events. A
  failed attempt retries with backoff a fixed number of times, then moves to `manual_resolution`.
- **Manual resolution screen** (admin): lists refunds stuck in `failed`, `manual_resolution` or in
  `processing` for more than 24 hours, shows the error, and lets staff retry or record that the
  refund was made outside the system, with who and when. Every change writes an audit row. An
  alert fires for any refund unresolved after 24 hours.
- **Notification.** Email and in-app message with the outcome (order confirmed, or refund started
  and, later, refund completed). SMS is reserved by the brief for codes and alerts, so it is not
  used here unless the client asks.

## Tests required (CLAUDE.md section 8)
Paid once; webhook replayed three times; amount mismatch; webhook before and after the redirect;
payment after expiry with stock available; payment after expiry with no stock; refund requested
once under concurrent triggers; refund retry then manual resolution; two buyers racing for the last
unit when one is a late payer.

## To confirm
1. Who bears any non-refundable Paystack processing fee on an automatic refund? Recommendation:
   the company. Check Paystack's current refund and fee rules when this is built; I have not
   verified them.
2. Guest customers: is an email address always collected, so the outcome can be sent? If not, the
   refund outcome needs another channel.
3. Refund timing is controlled by Paystack and the customer's bank or mobile money provider. The
   customer message must say it is started, not finished.
