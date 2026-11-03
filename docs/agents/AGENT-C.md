# Agent C: storefront

Read first, in order: `CLAUDE.md`, `docs/PROGRESS.md`, `docs/AUDIT-2026-11-02.md`, `docs/AGENTS-WORK-SPLIT.md`, then this file. If anything here conflicts with `CLAUDE.md`, `CLAUDE.md` wins and you stop and ask.

Status date: Monday 2 November 2026. Phase 1A, Week 5. Hand-over Friday 13 November 2026.

## 1. Role

Agent C builds the customer-facing website. Nothing exists yet: `web/storefront`, `packages/ui` and `packages/api-client` each contain only a `.gitkeep`. This is the largest piece of remaining work, so scope is the **thin launch path only**.

**Owns:** `web/storefront`, `packages/ui`, `packages/api-client`.
**Does not touch:** `backend/`, `infra/`, `.github/`, `docs/PROGRESS.md` outside your own section.

## 2. Start condition

You can start now. Nothing in `web/` or `packages/` overlaps with A or B, so scaffold on a branch from `main` in the `sk-agent-c` worktree: `c/<short-name>`. The generated API client needs the OpenAPI schema from the merged backend, so Agent A's "main is green and the chain is merged" report unblocks task 3 onward. Until then work on the scaffold and the design tokens.

## 3. Scope

**In (launch path):** product list, product page, cart, Buy Now, checkout, order tracking by reference and phone, phone-code login, guest checkout.
**Deferred, do not build:** filters polish, home-page extras, email login, Google sign-in, favourites, product video, saved addresses, reviews, anything from Phase 1B or later. If a design seems to need one of these, stop and ask.

## 4. Stack (fixed, from `CLAUDE.md` section 3)

TypeScript, Next.js App Router, Tailwind, pnpm workspaces, Vitest, Playwright, ESLint, Prettier. Any other library needs a one-paragraph dependency proposal first (what, why, alternatives, cost, maintenance). The Electro template is **reference only**; whether its markup can be reused is an open question for the human, so do not copy it.

## 5. Task list in order, with the evidence that counts as done

1. **Scaffold.** Next.js app in `web/storefront`, Tailwind, workspace links to `packages/ui` and `packages/api-client`, lint, type-check and test scripts, and a CI-ready build that passes. Do not edit `.github/`; ask Agent A to add a frontend job.
2. **Design tokens and base components** in `packages/ui` (colours, type scale, spacing, button, input, card, price display in GHS). One layout reused across pages. Mobile first.
3. **Typed API client** in `packages/api-client`, generated from the backend OpenAPI schema. Never edited by hand. If the schema is missing an endpoint or field, file a numbered request under `## Agent C` in `PROGRESS.md` and do not work around it.
4. **Product list and product page.** Show only the price tiers that are filled in. Prices come from the server. Show size and colour options from the product data.
5. **Cart and Buy Now.** The cart may live in the browser, but every price shown comes from the server's basket pricing endpoint. **The client never sends a price.**
6. **Checkout.** Contact details, delivery method (pickup, station, doorstep), delivery fee from the server quote, pay on delivery only where the server allows it (Accra doorstep), Paystack hosted checkout for online payment. The order becomes paid only on the server's confirmation, never because the browser returned from Paystack: the return page shows "checking your payment" and reads the order status.
7. **Order tracking** by reference and phone (the look-up endpoint), showing payment, fulfilment and refund status, and the delivery code once issued.
8. **Phone-code login** and guest checkout. Never log or store a one-time code in the browser beyond the form.
9. **Tests.** Vitest for components and helpers. Playwright for guest checkout and pay on delivery. Both are required before the storefront counts as done.
10. **Device pass:** a low-end Android on Chrome and an iPhone on Safari.

Proposed timing, human to confirm: tasks 1 and 2 on Monday and Tuesday, task 3 once the chain is merged, tasks 4 and 5 by Friday 6 November, tasks 6 to 8 in the week of 9 November, tests and device pass before Friday 13 November.

## 6. Blocked on the human

The **map provider** for the checkout map pin (open question 5). Stop at that step and ask. A fallback that avoids a map (typed address and station choice) is a business decision, so do not choose it yourself. Also waiting: the Electro template and credit decision, delivery fee settings, the station list, and Paystack test keys (for the end-to-end run).

## 7. Performance and quality budget

- Initial JavaScript under 200 KB. Fast first view on a mid-range Android over 4G.
- Responsive, lazy-loaded images with set dimensions. No layout shift.
- Accessible forms: labels, focus order, error messages in plain words.
- Money shown in GHS only, formatted from integer pesewas. Times shown in Africa/Accra.
- Never put secrets, keys or real customer data in the repo, logs, fixtures or tests.

## 8. Rules specific to this role

- No business rules in the client: no price maths, no fee maths, no stock decisions. Display what the server returns.
- Do not hide server errors. Show the standard error envelope's message in plain words.
- One concern per PR, small commits, branch names `c/...`.
- Stop and ask before: adding a dependency, changing a rule, building outside the launch path, or working around a missing endpoint.

## 9. Handoffs

- A to C: "main is green and the chain is merged", the OpenAPI schema location, a frontend CI job, the staging URL.
- B to C: each new or changed endpoint is noted under `## Agent B` in `PROGRESS.md` with an OpenAPI entry.
- C to B and A: numbered requests under `## Agent C` for missing endpoints, fields or CI changes.

## 10. Report format

Use the `CLAUDE.md` section 10 format at the end of every task, with real test output and, for UI work, a short list of the pages and states you checked.

## 11. Paste-in prompt

```
You are Agent C on the S.K Clothing platform. Work in the sk-agent-c worktree.
Read CLAUDE.md, docs/PROGRESS.md, docs/AUDIT-2026-11-02.md, docs/AGENTS-WORK-SPLIT.md and docs/agents/AGENT-C.md in full.
State the current phase, week and your first task, then list your open questions.
Post a short plan and wait for approval before writing code.
Work only in your own area. The client never sends a price. Do not invent business rules. Report using the CLAUDE.md section 10 format.
```
