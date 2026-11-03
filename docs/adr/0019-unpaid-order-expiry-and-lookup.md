# ADR 0019: Cancelling unpaid orders, and looking an order up again

Status: proposed. Items marked CONFIRM are my reading where the brief is silent.

## Cancelling orders that were never paid for
Checkout holds stock for 15 minutes (ADR 0017). Without a clean-up, an unpaid order would stay
"pending" for ever. `orders.expiry.cancel_stale_orders()` runs hourly (`apps.orders.tasks`) and
cancels them.

**It does not cancel at the moment the hold runs out.** ADR 0008 is the client's policy: a payment
that arrives after the hold must try to take the stock again, and refund only if it is gone. An
order cancelled at 15 minutes would refund every late payment, even when stock is available. So an
unpaid order gets a grace period first, during which it stays payable:
- online orders with a pending or failed payment: **24 hours**
- orders waiting for a staff quote: **72 hours**
- pay-on-delivery orders staff have not confirmed by phone: **72 hours**

Paid orders, and pay-on-delivery orders staff have confirmed, are never touched. A cancelled unpaid
order has its payment voided, no refund (no money was taken), and any hold still in place is
released. A cancelled order cannot be paid for any more (`order_closed`). If money still arrives for
one, for example the customer was already on Paystack's page, it stays cancelled and a refund is
requested (ADR 0018).

Payment and cancellation both lock the order row, so exactly one of them gets there first: a
payment that wins leaves the order paid and the cancel job skips it; a cancel that wins leaves the
order cancelled and the late payment is refunded. Running the job again, or several runs at once,
cancels each order once. The limits can be overridden with an `ORDER_EXPIRY_HOURS` setting.

## Looking an order up again
`POST /api/v1/orders/lookup/` with `reference` and `phone`. Guests have no account, so the phone
number the order was placed with is the proof. The answer shows the reference, the three statuses,
the totals and the lines. It never shows the phone number, name, address, keys or internal ids. A
wrong reference, a wrong phone number and a badly formed phone number all give the same 404, so it
cannot be used to find out which references exist. Look-ups are limited to 30 an hour per address
(`CHECKOUT_LIMITS` key `lookup_ip_rate`). References are typed in any case.

## Interpretations (CONFIRM)
1. The three grace periods above are my proposal. The brief gives none.
2. A signed-in customer's list of their own orders is not built; look-up is by reference and phone.
3. Look-up needs no Origin check: it changes nothing and sets no cookie.
4. Nothing tells the customer their order was cancelled. Notifications come with the messaging work.

## How it was checked
Against PostgreSQL 16.15. 408 tests in the whole scratch suite, 10 of them threaded tests of the
expiry job racing itself and racing a payment, with each side given a head start in turn so both
outcomes are tested; run 12 more times with no failures. A mutation check broke the code 17 ways
(grace periods, who may be cancelled, stock release, the lock against a payment, attribution,
batching, settings, the look-up's phone check, case handling, rate limit and leaking a phone
number), and every one was caught. Two further changes (letting paid or confirmed orders match the
cancel query) changed nothing, because the query also requires an order that is still pending; with
both conditions loosened together, the tests fail as they should. Not yet run in your CI.

## Not built yet
Refunds (starting one and tracking it, ADR 0008), telling customers about cancellations and refunds,
staff screens for mismatched and duplicate payments, a signed-in customer's order list, and
pay-on-delivery confirmation by staff.
