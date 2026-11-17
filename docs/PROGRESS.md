# Progress

## Current state
- Phase: Phase 0 (unfinished), Phase 1A (backend mostly built, storefront not started)
- Week: Week 5 (2 to 6 November 2026). Updated 2 November by Agent A.
- Stage 1 hand-over: Friday 13 November 2026 (confirmed by the human on 2 November). Test period 16 to 30 November, bug fixes only.
- Cut line status: thin launch path only. Deferred: filters, home-page polish, email login, Google sign-in, bulk import, refund staff screens, PWA extras. Human to confirm this list.
- Where things are: see docs/AUDIT-2026-11-02.md. Agent split: docs/AGENTS-WORK-SPLIT.md and docs/agents/.

## Deviations (human approved by request)
- All 14 backend app folders created empty (no code, not registered) ahead of their phases.
- Backend config, CI and Compose files created before PR 2 to 4.
- Six stacked branches merged through one PR (#3) so CI runs once over all of it, instead of one concern per PR (2 November).

## Deviations awaiting human approval
- Refunds (ADR 0020) are built but are not in the Phase 1A scope list.
- `backend/apps/orders/pickup.py` exists but pickup holds are Phase 2.
- Suppressions added to pass the type check: one `# type: ignore[attr-defined]` in `identity/login.py` (Agent B to remove) and one `# type: ignore[name-defined]` in `identity/forms.py` (gap in the Django type stubs). Generated migrations are excluded from type checking and from the line-length rule.
- Behaviour guards added to pass the type check: an order with no total is treated as awaiting quote (`orders/settlement.py`); an assert that a non-awaiting quote has a fee (`orders/checkout.py`); a login code check that succeeds without a user id is rejected (`identity/views.py`); `UserManager.get_by_natural_key(None)` raises DoesNotExist.

## Open questions
1. ~~Week 1 date mismatch: is Phase 0 already late?~~ Resolved 2 November: it is Week 5 and the date stands. Phase 0 is not finished.
2. ~~Approve a minimal payments app with the Paystack test webhook in Phase 0?~~ Resolved: approved, see Log, payments webhook.
3. Is the Electro template the design basis, or inspiration only?
4. Electro credit link: keep it if markup is reused, or buy credit removal?
5. Map provider for the checkout map pin. Blocks Agent C at the checkout step.
6. Delivery fee settings: base fee, rate per km, minimum fee, maximum distance, shop location.
7. Station list and fee per station.
8. ~~SMS provider (quotes pending).~~ Decided 2 November: Africa's Talking. Sender ID approval for Ghana pending. Email provider (Resend or Brevo) still undecided. Build against the fake providers meanwhile.
9. Product list or Excel, and return window per product type.
10. VPS plan size: processor, memory, disk.
11. Paystack test-mode account and keys, kept in secrets and never in the repo.
12. Production web server choice (needs a dependency proposal).
13. Later phases: WhatsApp coexistence in Ghana, printer and scanner models, opening finance figures, investor details.
14. Discounts: the log below says the definition is open, but ADR 0007 and `pricing/discounts.py` exist. Human to confirm the rule is settled.
15. How long do pay-on-delivery and awaiting-quote orders hold stock?
16. Staff two-factor: which library? Agent B to send a dependency proposal.
17. Are refunds and `orders/pickup.py` approved as in scope?
18. Wording of customer messages (order confirmation, delivery code, pickup reminder). Agent B drafts, human approves.
19. ADR 0015 is on a separate feature-flags branch (commits a763b4b and d1c42e2), not on refunds. Agent A to list all unmerged branches and the human to decide whether to merge them after PR #3.
20. A file named `pace written by cmd echo (fixes ruff I001)` is tracked in the repo root. Read on 2 November: it is `less` help text from a mistaken redirect, no code. Agent A to remove it in its own commit.

## Active tasks
- [x] PR 1: repo skeleton and docs (merged to main, GitHub remote exists)
- [ ] PR #3: merge the six stacked branches into main. Open. Ruff passes in CI. Type-check fixes pushed (commit 86b16e3), result to be confirmed. Django check, the migrations check and pytest have not run yet.
- [ ] See the per-agent sections below.

## Agent A
- [ ] Green CI on PR #3, then merge with a merge commit (not squash)
- [ ] Remove the stray root file after reading it; add docs/AUDIT-2026-11-02.md and docs/agents/
- [ ] Explain ADR 0015
- [x] Celery beat schedule: all five jobs are present in base.py (verified 2 November). Still to add: a test that fails if one is removed.
- [ ] Staging deploy from a merge to main
- [ ] Backups and restore drill (never cut)
- [ ] Sentry alerts, uptime monitor, Cloudflare
- [ ] Paystack test-mode run (needs keys)

## Agent B
- [ ] Waiting for PR #3 to merge
- [ ] Delivery code wiring (never cut)
- [ ] Notifications with outbox and Africa's Talking provider (never cut)
- [ ] Filters API
- [ ] Staff two-factor (dependency proposal first)
- [ ] Follow-ups from the type-check fixes (see Deviations awaiting human approval)

## Agent C
- [x] Scaffold Next.js, Tailwind and pnpm workspace in web/storefront (PR #5, Web CI green)
- [x] Design tokens and base components in packages/ui (shell and render tests are on their own branches, see Branches)
- [x] Browser cart, ids and quantities only (branch c/cart)
- [x] Checkout form matched to POST /api/v1/orders/, with the Mapbox location picker (branch c/map-picker). Not yet wired to the API or mounted on /checkout.
- [ ] Typed API client from the OpenAPI schema (needs the schema snapshot, request 3 below)
- [ ] Product list, product page, cart page, checkout wiring, tracking, phone login, guest checkout
- [ ] Playwright for guest checkout and pay on delivery; device pass

Branches (all stacked on c/scaffold):
1. c/scaffold (PR #5): scaffold, @sk/ui, header and footer, placeholder routes.
2. c/component-tests: render tests for @sk/ui (adds jsdom and Testing Library to @sk/ui).
3. c/cart: browser cart.
4. c/map-picker: checkout form matched to the API plus the Mapbox location picker. It contains the earlier c/checkout-form commit.
Merge order: 1 first, with a merge commit. Then 2 and 3 in either order. Then 4. Expect one pnpm-lock.yaml conflict between 2 and 4; resolve by merging main and running pnpm install.
Abandoned, do not merge: c/ui-tests (started from the wrong base, no packages) and c/checkout-form (replaced by c/map-picker).

Requests to Agent A (numbered, Agent C):
1. Root package.json: add "packageManager": "pnpm@12.16.1" and root scripts lint, typecheck, test, build, each "pnpm -r --if-present run <name>". Agent A is making this change; Agent C does not edit the root package.json.
2. Frontend CI job in .github/workflows/web-ci.yml: pnpm install --frozen-lockfile, then lint, typecheck, test, build. Node 22, pnpm 12.16.1. TypeScript is pinned to 6.x because typescript-eslint does not support 7.0. (Web CI passed on PR #5 at c93ef02.)
3. OpenAPI snapshot: run `python manage.py spectacular --format openapi-json` in CI and commit the result to packages/api-client/openapi.json (or publish it as a build artifact) whenever the backend API changes. Agent C generates the typed client from it. Local Docker is not an option on Agent C's machine.
4. Confirm how production routes /api/v1. The storefront's next.config.ts rewrites it to the backend (same origin, so session cookies, CSRF and the Origin check work). The checkout, login and payment endpoints run an Origin check, so staging and production must trust the storefront's origin.
5. NEXT_PUBLIC_MAPBOX_TOKEN must be set as a build-time variable for staging and production builds. The human adds those URLs to the token's allowed URLs in the Mapbox account.
6. Standalone output for Docker, if wanted: next.config.ts would set output "standalone" only when NEXT_OUTPUT=standalone, so local Windows builds are unaffected. Awaiting the human's yes.

Requests to Agent B (numbered, Agent C):
7. The order lookup response (POST /api/v1/orders/lookup/) has no delivery code. Tracking must show it once issued.
8. Quantity limits disagree: the price endpoint accepts up to 10,000 of one item, checkout up to 1,000.

Dependency proposals (Agent C):
- mapbox-gl 3.34.2 (runtime, @sk/storefront). Decision: the human chose Mapbox as the map provider and ran the install. Why: doorstep orders need a pinned location, which the server requires (latitude and longitude). Alternatives considered: Leaflet with MapTiler (about 42 KB gzipped against about 210 KB for a vector map library; recommended by Agent C) and Google Maps. Cost: free up to 50,000 map loads a month, then billed per 1,000; a card is required. Licence: version 2 and later is not open source and only works with Mapbox services. The map code is loaded lazily, so it is outside the initial JavaScript. Token variable: NEXT_PUBLIC_MAPBOX_TOKEN. It must be a public (pk.) token restricted to our URLs; the human confirms this. The map chunk size is not yet measured, because no page mounts the picker yet.
- openapi-typescript (dev, @sk/api-client): approved by the human, not yet installed. Waits for the schema snapshot.
- jsdom, @testing-library/react, @testing-library/dom, @types/react-dom (dev, @sk/ui): approved by the human, installed on c/component-tests.

Home page JavaScript baseline, 4 November: about 132 KiB gzipped (budget 200 KiB).

## Log
- Repo was first created nested by mistake and flattened. Old copy is in sk-clothing-old and can be deleted.
- staging.py and prod.py added after the first run failed to create them.
- Nothing has been linted, type-checked or tested yet. No dependencies are installed locally. (Superseded 2 November: see Log, 2 November.)

## Log, 2 November
- Status audit written (docs/AUDIT-2026-11-02.md). CLAUDE.md current state updated. Agent work split and per-agent briefs added.
- PR #3 opened. First CI run failed at ruff (12 findings). Fixed: import order, `__str__` placement and missing `__str__` on five models, line length excluded for generated migrations.
- Second CI run failed at mypy (16 errors in 8 files). Fixed in commit 86b16e3. Result to be confirmed.
- Local type-checking does not work on the human's machine (Django packages not installed); CI is the authority.

## Log, payments webhook
- Dates dropped as a concern by the human. Paystack is the gateway. payments app approved for the Phase 0 webhook.
- Webhook built: signature check, one row per event, replay safe. Not yet run in CI.
- Provisional: error envelope shape, rate limiting at Cloudflare or Nginx. See ADR 0002.

## Log, pricing
- resolve_price built as a pure function with Money. See ADR 0003.
- OPEN: how is a discount defined (percentage, amount off, or fixed price)? Discounts are not built until answered. (See open question 14.)

## Integration branch: catalog, photos core, inventory, discounts applied together for one CI run
- Deviation from one concern per PR, accepted to get one CI run over all unverified layers. See ADR 0004 to 0009.

## Domain core: delivery, order states, login codes, phone numbers
- Pure rules built and tested. See ADR 0010 and docs/BACKEND-PLAN.md. Items marked CONFIRM in ADR 0010 await the client.
- (A duplicate copy of this section was removed on 2 November. The two commits that produced it are 326bec5 and 5d333b6; the second only added these three lines.)

## Foundation: custom user model, error envelope, request IDs, readiness
- See ADR 0011. Staff two factor login is required by the brief and not built yet.

## Storefront browse API: categories, products, search, basket pricing
- See ADR 0012. Filters by size, colour and price range are not built yet.

## Delivery tables, admin screens and quote endpoint
- See ADR 0013. Client still to provide: shop location, doorstep fee values, maximum distance, station list. Enter them in the admin.

## Login by phone code
- Request and verify endpoints built on the OTP rules, with database-enforced limits, daily SMS cap, Origin check and session rotation. See ADR 0016. Migration comes from the [gen-migrations] workflow. Production cookie settings not yet reviewed. No real SMS provider yet.

## Login hardening
- Daily SMS allowance with 100 messages reserved for existing customers, 80% and used-up alerts, logout, who-am-I, purge of old login codes (task not yet scheduled), fake SMS refused under staging and production, explicit cookie settings and CSRF_TRUSTED_ORIGINS from the environment. See ADR 0016. Google sign-in and staff two-factor still await approval.

## Checkout
- POST /api/v1/orders/: idempotent, prices and quotes on the server, holds stock all-or-nothing, per-number open order limit. See ADR 0017. Needs a decision on how long pay-on-delivery and awaiting-quote orders hold stock. Payment, expiry cancelling and order lookup not built yet. (Payment, expiry and look-up are built in the sections below.)

## Order models and transition service
- Orders, lines, events and sub-orders built on the state machine. See ADR 0014. Cart, checkout and payment wiring come next.

## Payments
- Start a payment, confirm it with Paystack verify (webhook and return page), apply it to the order and its stock, late-payment rule from ADR 0008. See ADR 0018. Never run against real Paystack yet. Refunds, expiry cancelling and staff screens for mismatched or duplicate payments not built.

## Unpaid order expiry and order look-up
- Unpaid orders are cancelled after a grace period (24h online, 72h awaiting quote or unconfirmed pay on delivery) and their stock freed, hourly by Celery beat. Customers can look an order up with its reference and phone number. See ADR 0019. The beat schedule line is in base.py. Refunds are built (see Refunds below). Customer notifications are not built yet.

## Refunds
- Refunds are created, sent to Paystack once, followed up by polling, retried with pauses, and handed to a person when they cannot be delivered; staff can record a refund made outside the system. See ADR 0020. The two beat schedule lines are in base.py. Never run against real Paystack. Customer notification and a staff retry button not built.


## Update, 17 November 2026 (written by Claude with the human, append-only)

This section was added at the end so it cannot overwrite what the agents wrote above. Where it
disagrees with older text above, this section is newer.

### Merged into main
- PR #23 (b/finish-stage1): pack, dispatch and reissue-code staff actions, delivery fee screen,
  response shapes.
- PR #26 (b/delivery-code-sms): the customer SMS messages and the delivery code SMS, sent at
  dispatch and on staff reissue. It also carried the commits of PR #25.

### Open pull requests (check each one is green before merging)
- PR #27 (b/cancel-sms): texts the customer when an unpaid order is cancelled.
- PR #28 (b/refund-sms): texts the customer when a refund starts, and when it is handed to our
  team. A messaging problem can never block or undo a refund.
- PR #29 (b/quote-sms): staff can set the delivery fee on an order waiting for a quote, the
  customer is texted the total, and the awaiting-quote message is now sent at checkout.
  Includes a database migration (new Order.quoted_at and a new permission).

### Why PR #29 was needed
Orders for an unlisted station, or a doorstep address beyond the maximum distance, wait for a
quote. Nothing let staff give the quote, so those orders could never be paid. Also, unpaid
online orders were cancelled 24 hours after being placed, so a quote that took longer than a day
would have been cancelled at the next hourly run. The 24 hours now count from the quote.

### Decisions made
- The wording of the new SMS messages is approved by the human. The cancelled-unpaid wording says
  "not paid or confirmed in time" because the same task also cancels quote orders and unconfirmed
  pay-on-delivery orders.
- Awaiting-quote orders get a "ready to pay" text with the total once staff set the fee.

### Still to do after PR #29 merges
1. Give the staff group the permission "Can set the delivery fee on an order".
2. Set STOREFRONT_URL in the environment so the SMS can carry a link (it assumes the tracking
   page is at /orders). Without it the SMS says "Track and pay on our website."
3. Agent C: the order tracking page cannot take payment (OrderCard.tsx only shows the payment
   status). Customers who get the "ready to pay" text have nowhere to pay. See the brief.
   Until that ships, staff should not use the quote action on real orders.
4. Try the admin page once on staging: place an order for an unlisted station (for example
   Tamale), set the fee, and check the text. The page has not been seen in a browser yet.

### Open decision for Agent B
A delivery code SMS waiting to be sent keeps the plain code in OutboxMessage.body until it is
sent or fails for good (up to six tries, up to an hour apart). The delivery tables themselves
hold nothing that reveals the code. Confirm this is acceptable.

### Not built
- No message when a refund finishes, or when staff record a refund made outside the system.
- Real Africa's Talking provider (the Ghana sender ID approval is pending). Email provider.
- Staff two-factor login (dependency proposal first).
- Backups and restore drill (never cut). Scripts were written (ops/backup.sh, ops/restore-test.sh,
  ops/RESTORE-DRILL.md) but are not in the repo and have never been run. They need the VPS and an
  offsite place for the copies.
- Staging deploy, Sentry alerts, uptime monitor, Cloudflare, production routing of /api/v1.
- Paystack test-mode run: the payment and refund code has never run against real Paystack.
- Playwright specs and the device pass (low-end Android, iPhone).

### Needs something from the human or the client
Paystack test keys, delivery fee settings, shop location, station list and fees, VPS size,
product list and return windows, email provider, the website address.

### Working rules
- One small pull request per concern; stacked branches are retargeted to main as the one below
  them merges.
- Never log an SMS text, a phone number, a delivery code or an idempotency key.
- Run python -m ruff check . from backend before every commit. CI is the authority for tests
  (Django packages are not installed on the human's machine).
- A commit message containing [gen-migrations] makes CI generate the migration. CI's commit does
  not always start the checks; push an empty commit if the Checks tab shows 0.
