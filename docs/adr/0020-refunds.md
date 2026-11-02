# ADR 0020: Refunds

Status: proposed. Items marked CONFIRM are my reading where the brief or ADR 0008 is silent.

## What this change is
The refund half of ADR 0008. Money goes back to the customer, exactly once, and nothing is lost
track of. It covers three cases: a paid order that could not be fulfilled (ADR 0018), a paid order
that was cancelled, and a payment that arrived twice.

## How it works
1. **Finding what to refund** (`queue_refunds`). Orders whose refund status is `requested`, and
   payments marked `duplicate`, each get one `Refund` row, tied to the payment that succeeded. The
   link to the payment is unique, so a double trigger or several runners can never create a second
   refund for a payment. The amount is always the whole payment.
2. **Sending** (`submit_refund`). One runner claims the row under a lock and records the attempt
   first; only then is Paystack called, with no database transaction open. The amount is always
   stated in the request, so a repeated request can never refund more than was paid.
3. **Following up** (`sync_refund`). Every 5 minutes Paystack is asked how an open refund is
   getting on, and its answer decides. Refund webhooks are not used: I could not check their
   shape against the existing parser, and polling needs nothing the webhook would add.
4. **Trouble.** A refund that Paystack could not deliver is tried again after a pause (5 minutes,
   then 30), up to 3 attempts, and then goes to a person (`manual_resolution`). It goes to a person
   at once if Paystack refuses the request, or reports `needs-attention` (it needs the customer's
   bank details, which cannot be automated), or if a refund was sent and we never recorded the
   answer for 10 minutes (we cannot know whether it exists, and sending it again could refund
   twice).
5. **People.** Staff see refunds in the admin. For one that needs a person they can record that it
   was made outside the system (for example in the Paystack dashboard), with a required note. It
   is attributed to the staff member, logged, and applied to the order. Staff cannot edit amounts or
   statuses. A read-only list shows every payment, including the ones marked `mismatch` or
   `duplicate`.
6. **Alarm.** A refund unresolved after 24 hours raises an error in the logs every hour, which
   reaches Sentry. The message holds ids only.

A refund of an order moves the order's own refund status through the same steps (the state machine
in ADR 0010). A refund of a duplicate payment has no order status to move.

## Guarantees under simultaneous runs
Ten runners at once make one refund and send it once. Twelve refunds with six overlapping runners
each go out exactly once. These are tested on PostgreSQL.

## Decisions and interpretations (CONFIRM)
1. **Retry from "needs a person" is not offered to staff.** The order state machine (ADR 0010) has
   no step from `manual_resolution` back to `requested`, and changing that tested table is a
   separate decision. Staff can record a refund made outside the system. Proposal if you want a
   retry button: allow `refund_retry` from `manual_resolution`, with its tests.
2. The retry policy (3 attempts; pauses of 5 and 30 minutes; 10 minutes to call a sent refund
   stuck; polling every 5 minutes; alarm after 24 hours) is my proposal. All can be changed with a
   `REFUND_LIMITS` setting.
3. Payments marked `mismatch` (the wrong amount or currency) are not refunded automatically,
   because the right amount is unclear. They appear in the staff list.
4. Who bears any Paystack fee on a refund is still open (ADR 0008, "To confirm", point 1).
5. Telling the customer the outcome is not built (it needs the messaging work). The email stored
   on the payment attempt is what it will use.

## Unverified, and why it matters
Built from Paystack's documentation, read today: a refund is created with `POST /refund` (the
transaction reference and an optional amount); statuses are `pending`, `processing`, `processed`,
`failed` and `needs-attention`; a refund is fetched by its own id. **It has not been run against
Paystack itself.** Two assumptions rest on that:
- A second refund request for a transaction that is already fully refunded is refused. The design
  relies on it after a request that may or may not have got through: the second request either
  succeeds (the first never happened) or is refused (it did), and a refusal sends the refund to a
  person to check. If Paystack behaved differently, a refund could be sent twice, so test this in
  Paystack's test mode before trusting it with real money.
- After a `failed` refund, a new refund can be created for the same transaction.

## How it was checked
Against PostgreSQL 16.15. The refund client calls were tested against a small fake of Paystack's
server; everything else against an in-memory fake that refuses to refund more than was paid. 477
tests in the whole scratch suite, 5 of them threaded refund tests run 12 more times with no
failures. A mutation check broke the code 32 ways (claiming, locks, attempt counting, retry pauses
and limits, each Paystack status, the stuck case, resolving, the alarm, polling, the admin
screens and the client calls) and every one is caught. Three first slipped through (a retry pause
that was only enforced on one path, the staff member's id in the admin, and URL-safe refund ids) and
two more gaps were found by review before running; each needed a new test. Not yet run in your CI.

## Not built yet
Refund webhooks, telling the customer, a staff retry button, refunds for mismatched payments,
partial refunds, and the Paystack fee decision.
