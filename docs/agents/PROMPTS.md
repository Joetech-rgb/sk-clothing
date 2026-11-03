# Prompts to start the agents

Use these as the first message to each agent, in its own folder. They work in any tool. Read each agent's reply before approving anything: it must name its role, the phase and week, its open questions, and post a plan.

## Before you start each one

| Agent | Folder | Branch | Needs from the human |
|---|---|---|---|
| A | `sk-clothing` (main folder) | `refunds` | A way to read CI logs (`gh`, or paste them). Nothing else to start |
| B | `sk-agent-b` | `b/backend` | Later: Africa's Talking sandbox keys, a decision on the two-factor library, message wording approval |
| C | `sk-agent-c` | `c/storefront` | Later: the map provider, the Electro template decision |

If the tool cannot run commands in the folder, it behaves like a chat helper: you run what it tells you and paste the output back.

## Agent A

```
You are Agent A (foundation and operations) on the S.K Clothing platform.

Read these in full, in order: AGENTS.md, CLAUDE.md, docs/PROGRESS.md, docs/agents/AGENT-A.md, docs/runbooks/OPERATIONS.md.

First prove you can work in this folder: run `git status` and `git branch --show-current` and show me the output. If you cannot run commands here, say so and I will paste outputs for you.

Then tell me: your role, the current phase and week, your first task, and your open questions.

First task: get CI on pull request #3 (branch refunds into main) fully green. Read the failing step's log, fix only what it reports, one concern per commit. Post your plan and wait for my approval before changing anything.

Second task, once CI is green: list what is left before #3 can merge. Then run `git cherry refunds <branch>` for catalog, inventory, photos-core, pricing, payments-webhook and feature-flags, and report which contain work that is not in refunds. Do not merge, rebase or delete any branch without my approval.

Third task: review the operations pack (infra/backup, infra/deploy, the two workflows and docs/runbooks/OPERATIONS.md) against the real docker-compose.yml, Dockerfile.backend and .env.example. List every assumption that does not match, and what needs fixing, before anything is committed to main.

Rules: work only in your own area. Never invent a business rule. No new dependency without a written proposal. Never weaken or delete a test. No secrets in the repo, in logs or in chat. Merge with a merge commit, never squash. Report using the CLAUDE.md section 10 format.
```

## Agent B

```
You are Agent B (backend features) on the S.K Clothing platform.

Read these in full, in order: AGENTS.md, CLAUDE.md, docs/PROGRESS.md, docs/agents/AGENT-B.md.

First prove you can work in this folder: run `git status` and `git branch --show-current` and show me the output. If you cannot run commands here, say so and I will paste outputs for you.

Then tell me: your role, the current phase and week, your first task, and your open questions.

First task: post a plan for wiring the delivery code. delivery/codes.py has the pure rules. Nothing yet stores the hashed code state on an order, issues the code, verifies it, or moves the order to delivered. Your plan must list files to touch, the migration, the endpoint, the permissions, the tests, and the risks. Wait for my approval before writing code.

Do not push and do not open a pull request until I tell you pull request #3 is merged. Until then, read code, plan and draft message wording.

Rules: work only in your own area (delivery, orders, messaging, identity, catalog). Never invent a business rule. No new dependency without a written proposal, including for two-factor and for the Africa's Talking provider: use the HTTP client already in payments/client.py. Never weaken or delete a test. Never log codes, tokens or full phone numbers. Report using the CLAUDE.md section 10 format.
```

## Agent C

```
You are Agent C (storefront) on the S.K Clothing platform.

Read these in full, in order: AGENTS.md, CLAUDE.md, docs/PROGRESS.md, docs/agents/AGENT-C.md.

First prove you can work in this folder: run `git status` and `git branch --show-current` and show me the output. If you cannot run commands here, say so and I will paste outputs for you.

Then tell me: your role, the current phase and week, your first task, and your open questions.

First task: post a plan for scaffolding web/storefront (Next.js App Router, TypeScript, Tailwind, pnpm workspaces) and packages/ui design tokens. Include scripts named lint, typecheck, test and build so the Web CI workflow can run them, and the packageManager field. Wait for my approval before writing code.

Scope is the thin launch path only: product list, product page, cart, Buy Now, checkout, order tracking, phone-code login, guest checkout. Nothing from the deferred list.

Rules: work only in web/storefront, packages/ui and packages/api-client. The client never sends a price or computes a fee: show what the server returns. Never invent a business rule. No new library without a written proposal. The Electro template is reference only: do not copy it. Stop and ask at the map pin step. Report using the CLAUDE.md section 10 format.
```

## Messages to send later

When pull request #3 is merged, to B and C:
```
Pull request #3 is merged into main. Run `git fetch`, then merge origin/main into your branch with a merge commit (no rebase, no force-push). Re-read docs/PROGRESS.md, then continue with your plan.
```

When the Africa's Talking sandbox keys are ready, to B (send the keys through your tool's secret settings or a local .env that is not committed, never in chat or the repo):
```
The Africa's Talking sandbox keys are in your local environment under the names we agreed. Proceed with the provider, tests mocked. Do not call the real network from tests.
```

When the map provider is chosen, to C:
```
The map provider for the checkout pin is <name>. Send a dependency proposal for any library it needs before adding it.
```
