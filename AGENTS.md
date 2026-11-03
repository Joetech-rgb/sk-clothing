# Agent instructions

The standing brief for this repository is `CLAUDE.md`. Despite the file name, it applies to every agent, whatever tool runs it. It is the source of truth for scope, architecture, business rules and process.

At the start of every session, read these in full, in this order:

1. `CLAUDE.md`
2. `docs/PROGRESS.md`
3. Your role file:
   - Agent A (foundation and operations): `docs/agents/AGENT-A.md`
   - Agent B (backend features): `docs/agents/AGENT-B.md`
   - Agent C (storefront): `docs/agents/AGENT-C.md`

If you have not been told which agent you are, ask the human before doing anything.

Non-negotiable, repeated here because they matter most:

- Work only inside your own area. Shared files are edited only by Agent A.
- Never invent a business rule. If a rule is missing or unclear, write it under Open questions and stop on that item.
- Post a short plan (files, approach, tests, risks) and wait for approval before writing code.
- Add no dependency, Django app or service without a written proposal and approval.
- Never delete or weaken a test. Report real test output, including failures.
- No secrets, keys or real customer data in the repository, logs, fixtures or tests.
- Finish every task with the report format in `CLAUDE.md` section 10.

If this file and `CLAUDE.md` disagree, `CLAUDE.md` wins. Stop and ask.
