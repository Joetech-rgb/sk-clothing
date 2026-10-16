# ADR 0002: Paystack webhook records a minimal event row

Status: proposed

## Decision
The Phase 0 webhook verifies `x-paystack-signature` (HMAC-SHA512 of the raw body), then stores one row per event in `payments_paystackwebhookevent`. The row holds only event type, reference, amount (integer pesewas), currency and received time. The full payload is not stored.

De-duplication key is `event_type:reference`, enforced by a database unique constraint, so replays and concurrent deliveries cannot create two rows.

## Reasons
- Paystack payloads include customer and card details. We keep none of them (CLAUDE.md section 4, Security).
- A database constraint is safer than check-then-insert under concurrent retries.
- An empty `PAYSTACK_SECRET_KEY` rejects every request, so a missing secret can never accept unsigned traffic.

## Not done yet (needs orders)
- Confirming with server-side `transaction/verify`, matching the amount to an order, and marking an order paid. These arrive with the `orders` app in Phase 1A.

## Provisional
- The error body `{"error": {"code", "message"}}` is a placeholder until the standard error envelope is agreed.
- Rate limiting is not applied in the view. Plan: apply it at Cloudflare or Nginx for this path.
