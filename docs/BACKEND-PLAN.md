# Backend build plan (Phase 1A), in dependency order

Done means: written, tested, and CI green. Today nothing Django-based is CI green yet, because
the first integration CI run has not been reported. Pure cores are tested; Django layers are not.

## Business-rule cores (pure Python, tested, apply to the integration branch)
Pricing and discounts, photo processing, stock allocation and ledger rules, delivery fees,
delivery code, login code, phone numbers, order state machine, pickup timing, message-provider
and search interfaces, Paystack signature check.

## Django layers still to build
1. **Foundation (before the first staging database).** Custom user model `identity.User`: it must
   be chosen before any real database exists, because changing it afterwards is painful. Standard
   error envelope and DRF exception handler. Request IDs and logging with no personal data.
   Throttle classes (per IP, per number, daily SMS spend cap). Cursor pagination. A readiness
   endpoint that checks the database and Redis. OpenAPI and the typed client.
2. **identity:** user model, login-code request and verify, sessions, Google sign-in
   (`django-allauth`), password reset, audit rows.
3. **catalog read API:** categories, filters, sorting, product list and detail with filled tiers,
   stock left, PostgreSQL search behind `SearchService`, the Event table.
4. **delivery:** station table and doorstep settings in the admin, the quote endpoint, the
   delivery code stored on the order.
5. **orders:** cart (guest and logged in), Order, OrderLine, OrderEvent, idempotent checkout that
   prices with `price_cart`, quotes delivery, reserves stock and freezes every line; state changes
   only through `apply_event`; the Discount table and its admin; usage-limit counting.
6. **payments:** Paystack initialise and verify, webhook processing into orders with the amount
   check, late-payment handling and refunds (ADR 0008), pay on delivery.
7. **messaging:** outbox, real SMS and email adapters (after the providers are chosen), order
   notifications.
8. **admin back-office:** orders, quotes, uncollected decisions, refund resolution, stock watch.
9. **bulk import:** products and stock from a spreadsheet, through the existing services.
10. **Feature flags** table.
11. **Phase 0 operations:** production Compose with resource limits (ADR 0009), reverse proxy,
    deploy workflow, backups and the restore drill, monitoring. Needs the domain and accounts.

## Dependencies that need your approval (rule 6)
- `httpx` for calling the Paystack API (initialise, verify, refund).
- `gunicorn` as the production web server.
- `openpyxl` for the spreadsheet import.
- `django-allauth` is already in the fixed stack.

## Working rule from here
One concern per pull request again, once the first CI run is green.
