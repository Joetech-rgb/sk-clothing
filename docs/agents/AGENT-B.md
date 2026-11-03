# Agent B: backend features

Read first, in order: `CLAUDE.md`, `docs/PROGRESS.md`, `docs/AUDIT-2026-11-02.md`, `docs/AGENTS-WORK-SPLIT.md`, then this file. If anything here conflicts with `CLAUDE.md`, `CLAUDE.md` wins and you stop and ask.

Status date: Monday 2 November 2026. Phase 1A, Week 5. Hand-over Friday 13 November 2026.

## 1. Role

Agent B finishes the backend pieces that the launch path needs and that are not built yet: delivery code, notifications, staff two-factor, filters. B builds on the code that already exists and does not rewrite it.

**Owns:** `backend/apps/delivery`, `orders`, `messaging`, `identity`, `catalog` (filters and import).
**Does not touch:** `web/`, `packages/`, `infra/`, `.github/`, `backend/config/` (ask Agent A through `PROGRESS.md`).

## 2. Start condition

Do not start until Agent A reports "main is green and the chain is merged" (PR #3 merged into `main`). Then branch from `main` in the `sk-agent-b` worktree: `b/<short-name>`. Until then you may read code, write plans and draft message wording, but not push.

## 3. What already exists (do not rebuild)

- `delivery/codes.py`: pure rules for the delivery code (six digits, HMAC bound to the order, five attempts then locked, never log the code or hash). **Rules only. Nothing stores it, issues it or verifies it.**
- `messaging/providers.py` and `factory.py`: the `SmsProvider` and `EmailProvider` interfaces, result type with a retryable flag, and fake providers with idempotency keys. No real provider, no outbox, no sending on order events.
- `orders/`: states and transition table, checkout, expiry, look-up, settlement. `orders/pickup.py` exists but pickup holds are Phase 2: leave it alone.
- `identity/`: custom user model and phone-code login with hardening (daily SMS cap, customer reserve, alerts, origin check). No email and password login, no Google, no staff two-factor.
- `catalog/browse.py` returns size and colour in product data but does not filter by them.

## 4. Task list in order, with the evidence that counts as done

1. **Delivery code wiring. Never cut.** Store the hashed code state on the order (a migration, through the `[gen-migrations]` workflow). Issue a code when an order is ready for delivery. Show it on the order page and send it by SMS (`CLAUDE.md` section 5). Add a verify endpoint with the five-attempt lock. A correct code moves the order to delivered through the transition table and records who confirmed it. Delivery starts the return clock and the commission hold, so the transition must record the delivered time. Tests: right code, wrong code, lockout, replay, permissions (only a rider or staff), the code never appears in logs.
2. **Notifications. Never cut.** Add an outbox. Send on order events with an idempotency key so a retried job never sends twice. SMS only for OTP, order confirmation, the delivery code and internal alerts; everything else by email or in-app message. Build the Africa's Talking provider (section 5). Message wording is business content: draft it under Open questions and wait for approval.
3. **Filters API** by size, colour and price range in `catalog/browse.py`, with a query-count test so no N+1 appears. Filters apply to the existing list endpoint and are documented in OpenAPI.
4. **Staff two-factor (TOTP).** The brief requires it for staff and admin. This needs a library, so **send a dependency proposal first** (what, why, alternatives, cost, maintenance) and wait for approval. Do not add any package before the answer.
5. **Pay-on-delivery and awaiting-quote stock-hold rule.** Ask the human. Do not guess a duration.
6. Only if time remains: bulk product import, email and password login. Google sign-in is last (first on the cut line).

Every endpoint you add or change must appear in the OpenAPI schema so Agent C's typed client can be generated. Note each one in your section of `PROGRESS.md`.

## 5. Africa's Talking (SMS provider, decided by the human)

- Add `AfricasTalkingSmsProvider` behind the existing `SmsProvider` interface, selected through `messaging/factory.py` and settings.
- Read the official docs first (developers.africastalking.com/docs/sms/overview). Do not rely on memory for request fields or response codes.
- Use the HTTP client the project already uses (see `payments/client.py`). **No SDK and no new dependency without a proposal.**
- Settings from the environment: username, API key, sender ID, sandbox switch. Fake provider locally, sandbox in staging, real sending only in production. Staging and production must refuse the fake provider, as the login code already does.
- Never log the API key, message bodies or full phone numbers. Map responses to `SendResult` and set `retryable` correctly. Test with a mocked HTTP layer.
- The daily spend cap and the 100-message customer reserve from ADR 0016 still apply.
- Sender ID approval for Ghana may take several business days. The human is applying. If it is not approved by launch, ask Africa's Talking what sender messages will show instead of blocking.
- The email provider (Resend or Brevo) is undecided. Build against the fake.

## 6. Known follow-ups left by the CI fixes (yours)

- `identity/login.py`: `_customer()` is typed too loosely, so `user.pk` needed a `# type: ignore[attr-defined]`. Type its return value properly and remove the ignore.
- Three behaviour guards were added to make mypy pass. Review each and add a test if missing: `orders/settlement.py` treats an order with no total as awaiting quote (cannot be paid); `orders/checkout.py` asserts that a non-awaiting quote has a fee; `identity/views.py` rejects a successful code check that has no user id.
- `identity/models.py`: `get_by_natural_key(None)` now raises `DoesNotExist`. Add a test.

## 7. Rules specific to this role

- Business logic goes in each app's `services.py`. Views and serializers stay thin. Apps never import each other's models; call services. `import-linter` enforces it.
- No hard-coded fees, windows or limits that the brief says are admin settings.
- Never log OTPs, delivery codes, tokens or full phone numbers.
- Tests are required for order state transitions, webhook handling, permissions and anything touching delivery fees or stock. Never delete or weaken a test.
- Migrations are expand-then-contract. Never edit an applied migration.
- Stop and ask before: adding a dependency or a Django app, changing a business rule, building outside the phase, or touching production data.

## 8. Handoffs

- B to C: each new or changed endpoint gets an OpenAPI entry and a one-line note under `## Agent B` in `PROGRESS.md`.
- C to B: missing fields or endpoints arrive as numbered requests under `## Agent C`. Answer them there.
- B to A: any shared-file change (`base.py` beat lines, `urls.py`) goes as a numbered request under `## Agent B`.

## 9. Report format

Use the `CLAUDE.md` section 10 format at the end of every task, with real test output and pass and fail counts.

## 10. Paste-in prompt

```
You are Agent B on the S.K Clothing platform. Work in the sk-agent-b worktree.
Read CLAUDE.md, docs/PROGRESS.md, docs/AUDIT-2026-11-02.md, docs/AGENTS-WORK-SPLIT.md and docs/agents/AGENT-B.md in full.
State the current phase, week and your first task, then list your open questions.
Post a short plan and wait for approval before writing code. Do not start until Agent A reports main is green and the chain is merged.
Work only in your own area. Do not invent business rules. Report using the CLAUDE.md section 10 format.
```
