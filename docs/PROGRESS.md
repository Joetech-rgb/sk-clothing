# Progress

## Current state
- Phase: Phase 0, then Phase 1A (Stage 1)
- Week: UNCONFIRMED. Brief says Week 1 is 5 to 9 October 2026 but today is 15 October. Human to confirm.
- Stage 1 hand-over: 13 November 2026. Test period 16 to 30 November, bug fixes only.
- Cut line status: nothing cut yet

## Deviations (human approved by request)
- All 14 backend app folders created empty (no code, not registered) ahead of their phases.
- Backend config, CI and Compose files created before PR 2 to 4.

## Open questions
1. Week 1 date mismatch: is Phase 0 already late?
2. Approve a minimal payments app with the Paystack test webhook in Phase 0?
3. Is the Electro template the design basis, or inspiration only?
4. Electro credit link: keep it if markup is reused, or buy credit removal?
5. Map provider for the checkout map pin.
6. Delivery fee settings: base fee, rate per km, minimum fee, maximum distance, shop location.
7. Station list and fee per station.
8. SMS provider (quotes pending). Build against SmsProvider meanwhile.
9. Product list or Excel, and return window per product type.
10. VPS plan size: processor, memory, disk.
11. Paystack test-mode account and keys, kept in secrets and never in the repo.
12. Production web server choice (needs a dependency proposal).
13. Later phases: WhatsApp coexistence in Ghana, printer and scanner models, opening finance figures, investor details.

## Active tasks
- [ ] PR 1: repo skeleton and docs (committed locally, no GitHub remote yet)
- [ ] First CI run: fix whatever it reports

## Log
- Repo was first created nested by mistake and flattened. Old copy is in sk-clothing-old and can be deleted.
- staging.py and prod.py added after the first run failed to create them.
- Nothing has been linted, type-checked or tested yet. No dependencies are installed locally.

## Log, payments webhook
- Dates dropped as a concern by the human. Paystack is the gateway. payments app approved for the Phase 0 webhook.
- Webhook built: signature check, one row per event, replay safe. Not yet run in CI.
- Provisional: error envelope shape, rate limiting at Cloudflare or Nginx. See ADR 0002.

## Log, pricing
- resolve_price built as a pure function with Money. See ADR 0003.
- OPEN: how is a discount defined (percentage, amount off, or fixed price)? Discounts are not built until answered.

## Integration branch: catalog, photos core, inventory, discounts applied together for one CI run
- Deviation from one concern per PR, accepted to get one CI run over all unverified layers. See ADR 0004 to 0009.

## Domain core: delivery, order states, login codes, phone numbers
- Pure rules built and tested. See ADR 0010 and docs/BACKEND-PLAN.md. Items marked CONFIRM in ADR 0010 await the client.

## Domain core: delivery, order states, login codes, phone numbers
- Pure rules built and tested. See ADR 0010 and docs/BACKEND-PLAN.md. Items marked CONFIRM in ADR 0010 await the client.

## Foundation: custom user model, error envelope, request IDs, readiness
- See ADR 0011. Staff two factor login is required by the brief and not built yet.
