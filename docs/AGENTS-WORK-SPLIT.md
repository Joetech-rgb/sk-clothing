# Work split for three agents

Status: **PROPOSAL, human to approve before agents start.** Read together with `CLAUDE.md`, `docs/PROGRESS.md` and `docs/AUDIT-2026-11-02.md`. If anything here conflicts with `CLAUDE.md`, `CLAUDE.md` wins and you stop and ask.

Dates: today is Monday 2 November 2026. Stage 1 hand-over is 13 November **[HUMAN TO CONFIRM]**. The storefront is not started, so the plan below is the minimum launch path, not the full Phase 1A list.

## 1. Rules for working in parallel

1. Each agent works only inside its own area (section 3). If a task needs a file in another agent's area, stop and ask the human. Do not edit it.
2. **Shared files** (`backend/config/settings/base.py`, `backend/config/urls.py`, `docs/PROGRESS.md`, `CLAUDE.md`, `.github/workflows/*`) are edited only by Agent A, through small separate PRs. Other agents write what they need in their own section of `PROGRESS.md` under their heading and ask Agent A to apply the shared-file change.
3. `docs/PROGRESS.md`: each agent updates only its own section (headings: `## Agent A`, `## Agent B`, `## Agent C`).
4. One concern per PR. Branch names: `a/...`, `b/...`, `c/...`. Nobody pushes to `main` directly.
5. Do not start from the old stacked branches. Wait until Agent A reports that the chain is merged into `main` (Agent C may start in `web/` and `packages/` before that, since no files overlap).
6. Migrations go through the `[gen-migrations]` workflow, one agent at a time per app. Never edit an applied migration.
7. All of `CLAUDE.md` sections 1, 4, 5, 9, 10 and 11 apply. No invented business rules, no new dependencies without a proposal, plan before code, real test results only.
8. End every task with the report format from `CLAUDE.md` section 10.

## 2. Merge order (Agent A does this first)

`integration` -> `login-code` -> `checkout` -> `payments` -> `expiry` -> `refunds` -> `main`. One PR per branch in that order, CI green on each. Report the real result of each CI run. If a run fails, fix only what it reports.

## 3. Areas

| Agent | Owns | Must not touch |
|---|---|---|
| A, foundation and operations | `.github/`, `infra/`, `docker-compose.yml`, `backend/config/`, `docs/`, repo housekeeping | Business logic in apps |
| B, backend features | `backend/apps/delivery`, `orders`, `messaging`, `identity`, `catalog` (filters, import) | `web/`, `packages/`, `infra/` |
| C, storefront | `web/storefront`, `packages/ui`, `packages/api-client` | `backend/` |

## 4. Agent A: foundation and operations

Priority order:
1. Merge the six branches into `main` in order (section 2). Report CI results.
2. Fix CI failures, and run the whole backend test suite and report pass and fail counts.
3. Read the file named `pace written by cmd echo (fixes ruff I001)` in the repo root, report what it contains, then remove it in its own commit.
4. Explain the missing ADR 0015, or ask the human.
5. Apply the Celery beat lines that `PROGRESS.md` says are missing (expiry, refunds, login-code purge), then confirm they run.
6. Staging deploy from a merge to `main` (needs a deploy workflow and a web server config; a web server choice needs a dependency proposal first, open question 12).
7. Backups and a restore drill, documented with the real commands. **Never cut.**
8. Sentry project and alerts, uptime monitor, Cloudflare. These need the human's accounts and keys. Stop and ask.
9. Update `CLAUDE.md` section 0 and `PROGRESS.md` once the human confirms the dates.
10. Run the Paystack webhook and verify flow against test mode once the human supplies test keys. Keys go in secrets only.

## 5. Agent B: backend features

Wait for Agent A's merge report, then branch from `main`. Priority order:
1. **Delivery code wiring.** `delivery/codes.py` has the pure rules. Add: store the hashed code state on the order, issue a code when an order is ready for delivery, a verify endpoint with the five-attempt lock, and the move to delivered through the order transition table. Tests: right code, wrong code, lockout, replay, permissions. **Never cut.**
2. **Notifications.** Use the outbox and the `SmsProvider` and `EmailProvider` interfaces. Send on order events with an idempotency key. Build against the fake provider until the human chooses a provider. Message wording is business content: draft it, list it under Open questions and wait for approval. **Never cut.**
3. **Staff two-factor (TOTP).** Needs a dependency proposal first. Stop and ask before adding any library.
4. **Filters API** by size, colour and price range in `catalog/browse.py`, with an N+1 query check.
5. Pay-on-delivery and awaiting-quote stock-hold rule: ask the human, do not guess.
6. Only if time allows: bulk product import, email and password login. Google sign-in stays last (first on the cut line).
7. Every endpoint added is documented in OpenAPI so Agent C's client can be generated.

## 6. Agent C: storefront

Scope is the **thin launch path only**: product list, product page, cart, checkout, order tracking, phone login, guest checkout. Not filters polish, favourites, video, saved addresses or Google sign-in.

1. Scaffold Next.js (App Router), Tailwind and pnpm workspaces as in the fixed stack. No other libraries without a proposal.
2. Generate the typed client in `packages/api-client` from the OpenAPI schema. Never edit it by hand. If the schema is missing or incomplete, tell Agent A or B through `PROGRESS.md`, do not work around it.
3. Shared design tokens and components in `packages/ui`. One layout reused across pages.
4. Build in this order: product list, product page, cart, checkout (using the server quote and the order and payment endpoints), order tracking by reference and phone, phone-code login.
5. **The client never sends a price.** Prices and delivery quotes always come from the server.
6. Map pin at checkout is blocked on the map provider decision (open question 5). Stop and ask.
7. Performance: initial JavaScript under 200 KB, responsive lazy-loaded images. Check on a low-end Android on Chrome and an iPhone on Safari.
8. Add Playwright tests for guest checkout and pay on delivery.

## 7. Handoffs between agents

- A to B and C: "main is green and the chain is merged."
- B to C: each new or changed endpoint gets an OpenAPI entry and a one-line note in `PROGRESS.md` under `## Agent B`.
- C to B: any missing field or endpoint goes in `PROGRESS.md` under `## Agent C` as a numbered request. B answers there.
- Anyone blocked on a business rule writes it under **Open questions** and moves to the next task.

## 8. Daily check (human, 5 minutes)

```
git fetch --all
git log --oneline origin/main -10
```

Open the Actions tab and confirm `main` is green. Read each agent's section of `PROGRESS.md`. If an agent says it will miss a weekly exit check, decide the cut-line change that day.

## 9. Paste-in prompt for each agent

Use this as the first message. Change the letter.

```
You are Agent <A, B or C> on the S.K Clothing platform.
Read CLAUDE.md, docs/PROGRESS.md, docs/AUDIT-2026-11-02.md and docs/AGENTS-WORK-SPLIT.md in full.
Your area and task list are in section <4, 5 or 6> of AGENTS-WORK-SPLIT.md.
State the current phase, week and your first task, then list your open questions.
Post a short plan and wait for approval before writing code.
Work only in your own area. Do not invent business rules. Report using the CLAUDE.md section 10 format.
```
