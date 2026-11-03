# Agent A: foundation and operations

Read first, in order: `CLAUDE.md`, `docs/PROGRESS.md`, `docs/AUDIT-2026-11-02.md`, `docs/AGENTS-WORK-SPLIT.md`, then this file. If anything here conflicts with `CLAUDE.md`, `CLAUDE.md` wins and you stop and ask.

Status date: Monday 2 November 2026. Phase 0 unfinished, Phase 1A backend mostly built, Week 5. Hand-over Friday 13 November 2026.

## 1. Role

Agent A keeps `main` healthy and gets the project deployable. Nothing B or C builds counts until it is merged into a green `main` and runs on staging. A owns the pipeline, the infrastructure and the shared files.

**Owns:** `.github/`, `infra/`, `docker-compose.yml`, `backend/config/`, `docs/`, repo housekeeping.
**Does not touch:** business logic inside `backend/apps/`, `web/`, `packages/`. The only exceptions are changes CI forces (lint, types, migration checks), which are made in their own small commit and reported.
**Shared files only A edits** (through small separate PRs): `backend/config/settings/base.py`, `backend/config/urls.py`, `docs/PROGRESS.md`, `CLAUDE.md`, `.github/workflows/*`. B and C ask A in their section of `PROGRESS.md`.

## 2. Duty status (where Agent A stands today)

Important limit: the Agent A that has been working in the chat cannot touch the repository. It plans, writes scripts, reads logs the human pastes and reviews. The human runs every command and commits. Hands-on Agent A work happens in a Claude Code session in the `sk-agent-a` worktree, using the paste-in prompt in section 8.

| # | Duty | Status | Evidence and next step |
|---|---|---|---|
| 1 | Merge the six stacked branches into `main` | IN PROGRESS | PR #3 (`refunds` into `main`) is open with 16 commits, not merged. Merge method: merge commit, not squash |
| 2 | Fix whatever CI reports | IN PROGRESS | Ruff: 12 findings fixed and ruff passes in CI. Mypy: 16 findings fixed in commit `86b16e3`, result not yet confirmed. `manage.py check`, the migrations check and `pytest` have never run |
| 3 | The stray file `pace written by cmd echo (fixes ruff I001)` in the repo root | READ, NOT YET REMOVED | It is about 16 KB of help text from the `less` pager, saved by a mistaken redirect. No code and no secrets. Remove it in its own commit |
| 4 | ADR 0015 missing from this branch | FOUND ON ANOTHER BRANCH | `git log --all` shows ADR 0015 in commits `a763b4b` ("Add feature flags with audit trail") and `d1c42e2` ("Test flag permissions and audit attribution; register flags app"). Neither is on `refunds`, so a feature-flags branch exists outside PR #3. List all branches, see what else is unmerged, and ask the human whether it is needed for launch |
| 5 | Celery beat lines (expiry, refunds, login-code purge) | DONE | `base.py` already schedules all five jobs: expire stock reservations, purge old login codes, cancel stale orders, process refunds, check overdue refunds. Still to verify: that each task path exists and a test fails if one is removed |
| 6 | Staging deploy from a merge to `main` | NOT STARTED | No deploy workflow. `infra/` has only `Dockerfile.backend` |
| 7 | Backups and restore drill (never cut) | NOT STARTED | Nothing found in the repo |
| 8 | Sentry project and alerts, uptime monitor, Cloudflare | NOT STARTED | Code is wired for Sentry. Accounts and alerts unconfirmed. Needs the human's accounts |
| 9 | Update `CLAUDE.md` and `docs/PROGRESS.md` | PARTLY DONE | `CLAUDE.md` section 0 and the SMS line are updated and committed. `PROGRESS.md` is updated and committed (482388e). `docs/agents/AGENT-B.md` and `AGENT-C.md` are in the working folder but not yet committed. `AGENT-A.md` and `docs/AUDIT-2026-11-02.md` are not in the repo yet |
| 10 | Paystack webhook and verify against test mode | NOT STARTED | Needs test keys from the human, kept in secrets |
| 11 | Install and enable `gh` or equivalent | OPTIONAL | Not installed. The browser works |

Created so far by the chat Agent A: `AUDIT-2026-11-02.md`, `AGENTS-WORK-SPLIT.md` (committed), the updated `CLAUDE.md` (committed), the ruff fix script and the mypy fix script (both applied and deleted).

## 3. Task list in order, with the evidence that counts as done

1. **Green CI on PR #3.** Done when all steps (ruff, mypy, check, migrations check, pytest) pass on the latest commit, and you have reported the pytest pass and fail counts. If `pytest` fails, fix only what it reports, one concern per commit.
2. **Merge PR #3** with a merge commit. Tell B and C: "main is green and the chain is merged."
3. **Housekeeping PR:** remove the stray file (it is `less` help text, no code), add `docs/AUDIT-2026-11-02.md` and `docs/agents/`, and settle ADR 0015 (it lives on a feature-flags branch: list every unmerged branch with `git branch -a` and decide with the human which need to join `main`).
4. **Beat schedule:** all five jobs are already in `CELERY_BEAT_SCHEDULE`. Confirm each task path imports, and that a test fails if a job is removed or renamed.
5. **Staging deploy:** a merge to `main` deploys to the VPS through Docker Compose behind Cloudflare. A web server choice needs a dependency proposal first (open question 12). Done when a merge changes staging without a manual step.
6. **Backups and restore drill. Never cut.** Scheduled database and media backups, a documented restore, and a drill performed and recorded with the date and time taken. Done only when the restore has actually been done once.
7. **Monitoring:** Sentry receiving a test error, an uptime monitor on the health endpoint, an alert reaching a human. Needs the human's accounts.
8. **Paystack test mode:** run the webhook and verify flow with real test keys. Replay the webhook three times and confirm the order is paid once.
9. **Go-live checklist** (Week 6): build it from `CLAUDE.md` section 9, and get it signed after the restore drill and the device pass.

Proposed timing, human to confirm: tasks 1 to 3 by Tuesday 3 November. Task 4 on Wednesday. Tasks 5 and 6 by Friday 6 November. Tasks 7 and 8 in week 6, while the human sets up accounts and keys.

## 4. Rules specific to this role

- Merge method is a **merge commit**, never squash, so commit hashes stay the same for B and C.
- Make no change to business logic unless CI forces it. Report every such change. Never weaken or delete a test.
- Never log, commit or paste secrets. The CI database password is a throwaway. No real key goes in the repo.
- A migration that is applied anywhere shared is never edited.
- Destructive operations and anything touching production data need the human's approval first.
- Suppressions (`# noqa`, `# type: ignore`) are allowed only with a reason in the commit and a note in `PROGRESS.md`. Open suppressions so far: one `# type: ignore[attr-defined]` in `identity/login.py` (B to remove), one in `identity/forms.py` (stubs gap).
- Behaviour guards added while fixing mypy, to keep in mind during review: an order with no total is treated as awaiting quote (`settlement.py`); an `assert` that a non-awaiting quote has a fee (`checkout.py`); a login code check that succeeds without a user id is rejected (`identity/views.py`).

## 5. Blocked on the human

Hand-over date confirmation (done: 13 November), Paystack test keys, Sentry, Cloudflare, uptime and VPS access, Africa's Talking sandbox keys for B, the map provider for C, the Electro template and credit decision, whether refunds and `orders/pickup.py` are approved as in scope, and the staff two-factor library for B.

## 6. Handoffs

- A to B and C: "main is green and the chain is merged", then the staging URL once deploy works.
- A to B: beat schedule lines applied, OpenAPI endpoint path.
- B or C to A: a numbered request in their section of `PROGRESS.md` for any shared-file change.

## 7. Report format

Use the `CLAUDE.md` section 10 report format at the end of every task. Include real command output for tests and CI, and say plainly when something is unverified.

## 8. Paste-in prompt for a hands-on Agent A session

```
You are Agent A on the S.K Clothing platform. Work in the sk-agent-a worktree.
Read CLAUDE.md, docs/PROGRESS.md, docs/AUDIT-2026-11-02.md, docs/AGENTS-WORK-SPLIT.md and docs/agents/AGENT-A.md in full.
State the current phase, week and your first task, then list your open questions.
Post a short plan and wait for approval before changing anything.
Work only in your own area. Do not invent business rules. Report using the CLAUDE.md section 10 format.
```
