# ADR 0021: The delivery code is derived, not stored as a hash

Status: proposed. Items marked CONFIRM are my reading of the brief where it is silent.

## Decision
The six-digit delivery code is worked out on demand from a random nonce stored per order and a
server secret, the way one-time passwords are (RFC 4226 style: HMAC-SHA256 of the order id and the
nonce, truncated to six digits). The database stores the nonce, the failed-attempt count and a
locked flag. It does not store the code or a hash of it.

## Why
CLAUDE.md section 5 says the code is stored as an HMAC and is also shown on the order page and sent
by SMS. A hash cannot be shown again, so both cannot be literally true. Deriving the code keeps what
the HMAC was for: a copy of the table is useless without the server secret, and a code for one order
does not work for another. The customer can see the code again if the SMS is lost.

## Rules kept
Six digits. Five wrong attempts then locked, even against the right code. Input that is not six
digits is not a guess. The code, the submitted value and the nonce are never logged.

## What it adds
- Entering the right code (rider or staff) moves the order to delivered through the transition
  table, in the same database transaction, and records who confirmed it and when. `delivered_at`
  is set by the transition itself, so every route to delivered records it. It starts the return
  clock and the commission hold.
- The wrong-guess count is saved even when the answer is a refusal (the service returns the
  outcome instead of raising inside the transaction).
- Repeating a correct code is a harmless no-op. Two riders submitting at once deliver the order once
  (the order row is locked).

## CONFIRM
1. **Who may confirm.** An active account holding the `delivery.confirm_delivery` permission. An admin
   gives it to a "delivery rider" group and to staff. Superusers have it automatically. The brief
   says "rider or staff" and does not define the accounts.
2. **Lockout.** After five wrong attempts only staff can reissue a code (a new nonce, so a new code),
   and it is recorded. The brief gives no unlock rule.
3. **The code shows on the order page** to anyone who can look the order up (reference plus phone),
   only while the order is out for delivery, and not while locked.
4. **Key.** Derived from SECRET_KEY with its own label. Rotating it changes every code still waiting
   to be used, so a separate setting with key versions is a follow-up.

## Not built yet
Issuing the code when an order is dispatched, sending it by SMS, and the staff screens to pack,
dispatch and reissue. Those come in the next pull request.
