# ADR 0017: Checkout

Status: proposed. Items marked CONFIRM are my reading where the brief is silent.

## What this change is
`POST /api/v1/orders/` places an order: it prices the basket, quotes delivery, holds the stock and
freezes the order, all in one transaction. It builds on the order records (ADR 0014), the stock
rules (ADR 0006), the delivery quote (ADR 0013) and the Origin check from the login work
(ADR 0016). Payment is not part of it: the order is created unpaid and waiting.

## Request and answer
- Header `Idempotency-Key` (8 to 64 letters, digits, `_` or `-`) is required.
- Body: `items` (variant id and quantity, at most 50 lines, 1 to 1000 each), `delivery` (`pickup`,
  `station` with `station_name`, or `doorstep` with `latitude`, `longitude` and `address`),
  `contact_name`, `contact_phone` (a Ghana number) and `payment_method` (`online` or `cod`).
- Answer `201` for a new order and `200` for a retry, with the reference, the three statuses,
  subtotal, delivery fee, total (fee and total are `null` while awaiting a quote), the lines as
  frozen, and `stock_held_until`. No contact details, internal ids or keys are returned.
- Refusals carry a stable `details.reason`: `idempotency_key_required` (400),
  `idempotency_conflict` (409), `insufficient_stock` (409, with `variant_id` and `available`),
  `variant_unavailable` (422), `cod_not_available` (400), `too_many_open_orders` (429),
  `bad_origin` (403). Bad input is `400` with field details.

## Guarantees, and what enforces each
- **The browser never names a price or a fee.** It sends ids and quantities only; every figure
  comes from `price_cart` and the delivery quote, and unknown fields are ignored.
- **A retry is safe.** The same key and the same request returns the same order and holds stock
  once. The same key with a different request is refused (`409`). A request is compared by a hash
  of what was asked for, after repeated variants are added together and phone, name and station
  spacing are normalised.
- **Keys are private to the customer.** The stored key is a hash of the signed-in customer (or
  "guest") plus the key, so nobody can fetch another customer's order by guessing a key, and the
  raw key is never stored.
- **All or nothing.** The stock hold and the order are written in one transaction. A failure after
  the hold takes the hold back.
- **The last unit sells once.** Inventory locks stock rows in a fixed order, so two buyers cannot
  both take it and two baskets cannot deadlock each other.
- **One number cannot tie up stock.** At most 3 unpaid orders per phone number inside the 15-minute
  hold window, counted under a per-number lock so simultaneous requests cannot slip past. A retry is
  never counted as a new order. Per caller address, 30 checkouts an hour. Both can be overridden
  with a `CHECKOUT_LIMITS` setting.
- **Cross-site pages cannot order.** The same Origin check as the login endpoints. Signed-in
  customers are recognised from the session cookie without a CSRF token; the Origin check stands in
  for it.

## Interpretations (CONFIRM)
1. Guest checkout is allowed. A name and a Ghana phone number are required for every order,
   including pickup.
2. **Pay on delivery and orders awaiting a quote hold stock for the standard 15 minutes.** Staff
   confirm pay-on-delivery orders by phone and set quotes by hand, which may take longer. After the
   hold ends the stock can be sold to someone else. This needs a decision: a longer hold for these
   orders, or the re-reserve rule of ADR 0008 when staff confirm.
3. Pay on delivery is allowed only when the quote allows it (a priced doorstep order), as ADR 0010.
4. The delivery address, map pin and station are stored on the order (`delivery_details`). That is
   personal data; how long to keep it is not decided.
5. The order line names come from a new catalog service, `variant_labels`, such as
   "Red shirt - M, Red".
6. The open-order limit counts pay-on-delivery orders and orders awaiting a quote as open.
7. Two orders from the same number and the same basket with different keys are two orders.

## Depends on
The order records (`orders-models`, ADR 0014) and the login work (`login-code`, ADR 0016), because
the view uses `apps.identity.origin` and `apps.identity.phone`. Merge those first.

## How it was checked
Against PostgreSQL 16.15, with your real inventory, catalog, delivery and money code as pasted. A
stand-in was used for `allocation.py`, the delivery tables and `resolve_price` (retail only), none
of which checkout changes. 112 orders tests, 10 of them threaded concurrency tests (up to 30
simultaneous buyers); the concurrency tests were run 28 times with no failures. A mutation check
broke the code 26 ways: 24 were caught directly. Two survive as equivalent changes: Django's
session backend already refuses switched-off accounts, and the open-order query already excludes
paid orders by status. The testing found and fixed a real bug: signed-in customers were being
treated as guests, because Django REST framework replaces the request's user while it works. Not
yet run in your CI.

## Not built yet
Paying (Paystack initialise and verify), confirming the stock hold when payment arrives, cancelling
unpaid orders and releasing their stock when the hold expires, a way for a customer to look an order
up again, the delivery code, setting a staff quote, the cart, and the discount table.
