# ADR 0018: Paying for an order

Status: proposed. Items marked CONFIRM are my reading where the brief is silent.

## What this change is
Two endpoints and a webhook that take an order from "unpaid" to "paid", on top of the Paystack
webhook from ADR 0002, the order records (ADR 0014), checkout (ADR 0017) and the late-payment
policy (ADR 0008):
- `POST /api/v1/payments/initialize/` with `order_reference` and `email`: starts a payment and
  returns `authorization_url`, the Paystack page to send the customer to, and a `reference`.
- `GET /api/v1/payments/verify/?reference=...`: the page Paystack sends the customer back to
  calls this. The server asks Paystack what happened, applies it, and answers with the order's
  statuses.
- The webhook: for `charge.success`, the server asks Paystack and applies the answer.

## Rules, from Paystack's documentation and the brief
- **The amount is the order total, read from the order.** A client never names it. Amounts are
  whole pesewas and the currency is GHS.
- **Nothing marks an order paid except `transaction/verify` saying `success`** with exactly the
  attempt's amount and currency, for the same reference. The body of a webhook and the page a
  customer returns to are only hints to go and ask. A webhook claiming success is not believed if
  Paystack says otherwise, and a webhook cannot name the amount.
- **Applying a payment is safe to repeat and to run at the same moment.** The result of the verify
  call is applied under a row lock on the attempt, with no database transaction open while waiting
  for Paystack. The same payment reported by the webhook three times and the return page twice sells
  the stock once and writes one `payment_confirmed` event.
- **A webhook that could not reach Paystack answers 503, so Paystack sends it again, and the repeat
  is allowed to finish the job** even though the event is already recorded as seen. (Confirming runs
  on every delivery, not only the first.)
- **A payment for an order that was already paid is never lost and never sold twice.** The attempt
  is marked `duplicate` and an error is logged (it reaches Sentry), so a person can refund it.
- **A wrong amount or currency is never applied.** The attempt is marked `mismatch` and an error is
  logged. The webhook still answers 200, because retrying cannot fix it.

## What payment does to the order and its stock (ADR 0008)
- Hold still active: the held stock becomes a sale.
- Hold expired or released: the old holds are released, the stock is reserved again and sold, in
  the same transaction.
- No stock left: nothing is oversold. The order becomes paid, not fulfillable, with a refund
  requested.
- Order cancelled before the money arrived: it stays cancelled and a refund is requested.
- A failed attempt marks the order payment as failed, keeps the stock held, and the customer may
  try again (up to 5 attempts per order). A failed attempt cannot undo a payment that succeeded.

## Decisions and interpretations (CONFIRM)
1. **The email is collected at the payment step, not at checkout,** because Paystack requires one
   and guests have only a phone number. It is stored on the payment attempt, because Paystack and
   the refund message in ADR 0008 need it. How long to keep it is not decided.
2. **No new dependency.** The Paystack client uses Python's standard library. If you later approve
   `httpx`, only `client.py` changes.
3. Anyone holding an order reference (ten characters, about 50 bits) can start a payment for it or
   see its statuses. No contact details, amounts or internal ids are shown.
4. Settings: `PAYSTACK_CALLBACK_URL` (optional, where Paystack sends the customer back; otherwise the
   dashboard setting applies), `PAYMENT_LIMITS` (overrides the attempt limit and the per-address
   rates: 20 starts and 60 return-page checks an hour). `PAYSTACK_CLIENT="fake"` is for tests and is
   refused under the staging and production settings.
5. The stock hold for pay-on-delivery and awaiting-quote orders is still undecided (ADR 0017).

## How it was checked
Against PostgreSQL 16.15, with your real webhook code and the real order, checkout and inventory
code. The Paystack client was tested against a small fake of Paystack's server running on the test
machine, and everything else against an in-memory fake. **It has not been run against Paystack
itself**, with test keys or otherwise; Paystack's real answers may differ in details. 108 payments
tests, 11 of them threaded concurrency tests, run 12 more times with no failures. They include a
late payer racing a new buyer for the last unit, with each side given the head start in turn so both
outcomes are tested. A mutation check broke the code 37 ways (amount, currency and reference
checks, repeat handling, locks, the late-payment rule, payability rules, the webhook, throttles and
the client), and every one was caught. Not yet run in your CI.

## Not built yet
Starting a refund and tracking it (ADR 0008), cancelling unpaid orders and releasing their stock when
the hold expires, telling the customer the outcome, a way for staff to see and resolve mismatched and
duplicate payments, looking an order up again, and pay-on-delivery confirmation.
