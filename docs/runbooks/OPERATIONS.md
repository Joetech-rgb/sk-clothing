# Operations runbook: staging, backups, restore drill, monitoring

Owner: Agent A. Status date: 2 November 2026. Items marked **[CONFIRM]** need the human or a look at the real server or repo; nothing below invents a decision that belongs to the client.

## 0. What is in the repo for this (and what was tested)

| File | What it does | Tested how |
|---|---|---|
| `infra/backup/backup.sh` | Dump the database, prove it is readable, keep 7 daily and 4 weekly copies, optional off-site copy and alert hooks | Run against a real PostgreSQL 16 with a stand-in for `docker compose exec`: success, failing dump, failing off-site copy, pruning |
| `infra/backup/restore.sh` | Restore a backup into a throw-away database, check it, write the result to `drill.log` | Same setup: good dump passes; truncated dump, wrong checksum and a missing table all fail and are logged |
| `infra/deploy/deploy.sh` | Backup, build, migrate, start, wait for healthy, roll back on failure | Simulated with git commits and a local web server: success, wrong commit, failed migration, unhealthy start, failed backup |
| `.github/workflows/deploy-staging.yml` | After CI passes on `main`, runs `deploy.sh` on the staging server over SSH | Checked with `actionlint`. **Never run against a real server** |
| `.github/workflows/web-ci.yml` | Lint, type-check, test and build the storefront. Does nothing until `web/storefront/package.json` exists | Checked with `actionlint` |

Not tested: anything that needs your real server, Docker, Cloudflare or GitHub secrets. The first real run will find problems. That is what the drill is for.

## 1. Staging server setup (the human, once)

Assumptions to check first **[CONFIRM]**:
- `docker-compose.yml` was written for local work. A production compose file, and the production web server choice (open question 12), come first. Put its name in `STAGING_COMPOSE_FILE`.
- The Django service in compose is called `backend` and the database `db`. Read `docker-compose.yml` and set `STAGING_APP_SERVICE` and `STAGING_DB_SERVICE` if they differ.
- The readiness endpoint address (ADR 0011) goes into `STAGING_HEALTH_URL`. It must answer 200 only when the app and database are working.

On the server:
1. Install Docker with the Compose plugin. Create a non-root deploy user and add it to the `docker` group.
2. Clone the repository into a fixed folder (for example `/srv/skclothing`) using a **read-only GitHub deploy key**.
3. Create the server's `.env` from `.env.example`. **Never commit it and never paste it into chat.** Put real secrets only here.
4. Make `/var/backups/skclothing` writable by the deploy user.

On your own machine, make a key pair used only for deploying:
```
ssh-keygen -t ed25519 -f sk_deploy_key -C "github-actions-deploy" -N ""
```
Put `sk_deploy_key.pub` into the deploy user's `~/.ssh/authorized_keys` on the server. Keep `sk_deploy_key` (the private half) for the GitHub secret below, then delete it from your machine.

Get the server's host key from a machine you trust, and check the fingerprint matches what the server shows:
```
ssh-keyscan -p 22 your.server.address
```

In GitHub: Settings, Environments, create one named **staging**. Add:

| Secrets (environment) | Meaning |
|---|---|
| `STAGING_HOST` | Server address |
| `STAGING_USER` | The deploy user |
| `STAGING_SSH_KEY` | Contents of `sk_deploy_key` (the private key) |
| `STAGING_KNOWN_HOSTS` | Output of `ssh-keyscan` |
| `STAGING_SSH_PORT` | Only if not 22 |

| Variables (environment) | Meaning |
|---|---|
| `STAGING_PATH` | Folder of the clone, for example `/srv/skclothing` |
| `STAGING_HEALTH_URL` | The https readiness address |
| `STAGING_COMPOSE_FILE`, `STAGING_APP_SERVICE`, `STAGING_DB_SERVICE` | Only if not the defaults |

Then add one **repository** variable (Settings, Secrets and variables, Actions, Variables): `STAGING_DEPLOY_ENABLED` = `true`. Until this is set the workflow does nothing, so merging it is safe.

First deploy: Actions, "Deploy staging", Run workflow, branch `main`. Read the log. Expect to fix a few things.

## 2. Backups

Run from the repository folder on the server. Accra is on GMT all year, so cron's UTC clock is Accra time:
```
15 2 * * * cd /srv/skclothing && COMPOSE_FILE=<your compose file> bash infra/backup/backup.sh >> /var/log/skclothing-backup.log 2>&1
```

Decisions for the human **[CONFIRM]**:
- **Retention.** Defaults are 7 daily and 4 weekly copies. Change with `KEEP_DAILY` and `KEEP_WEEKLY`.
- **How much can we lose?** A daily backup means up to 24 hours of orders could be lost in a disaster. If that is too much, back up more often. Paystack keeps its own record of payments, so money can be reconciled against it, but orders themselves cannot be recovered from it.
- **Off-site copy.** Without it the script prints a warning and the backup dies with the server. Cloudflare R2 is already in the stack. `OFFSITE_COMMAND` is a script that receives the dump path and its checksum path and copies them to a private bucket. A sketch, **untested**:
  ```
  #!/usr/bin/env bash
  set -euo pipefail
  for f in "$@"; do rclone copyto "$f" "r2:skclothing-backups/$(basename "$f")"; done
  ```
  This needs `rclone` installed on the server (a tool, not a repo dependency, but still your call) and its credentials set up outside the repo.
- **Encryption.** Dumps contain customer phone numbers and addresses. Encrypt them before they leave the server, and keep the bucket private. Choose the method and where the key lives before launch.
- **Product photos** live in R2, not in the database. Check that bucket's own protection (versioning or a second copy).

Make failures noticed. Set `ON_FAILURE_COMMAND` to something that reaches a person. Set `ON_SUCCESS_COMMAND` to ping an uptime service's heartbeat address, so a backup that silently stops running raises an alert too.

## 3. Restore drill (never cut)

A backup has not been proven until it has been restored. Do this on staging before go-live, and again after any change to backups.

```
cd /srv/skclothing
bash infra/backup/backup.sh
bash infra/backup/restore.sh /var/backups/skclothing/daily/<newest file>.dump
cat /var/backups/skclothing/drill.log
```

It passes when: the output ends with `RESTORE DRILL RESULT: PASS`, the table counts look right compared with the live database at the time of the backup, and `drill.log` has the new line. Also do it once from the **off-site** copy, on a machine other than the server, so you know the copy is usable.

Record each drill here:

| Date and time | Who | Backup file | Source (server or off-site) | Restore seconds | Result | Problems found |
|---|---|---|---|---|---|---|
| | | | | | | |

## 4. A real disaster restore (manual, supervised, not scripted)

Never run this alone and never first on production. Outline:
1. Stop the app containers so nothing writes. Keep the database container.
2. If the damaged database is still readable, take one more dump of it first.
3. Create a new empty database. Restore the chosen dump into it with `pg_restore --no-owner`.
4. Run `python manage.py migrate` with the code version that matches the dump.
5. Start the app. Check the readiness address, place a test order, check the stock numbers.
6. Reconcile payments from the last backup time to now against the Paystack dashboard. The webhook and verify code is safe to replay.
7. Write down what happened, the times, and what was lost.

## 5. Monitoring checklist (the human has to own the accounts)

- [ ] Sentry project created. Its address is set as an environment value on the server (find the variable name in `.env.example` and `config/settings`). A deliberate test error appears in Sentry with a request ID.
- [ ] An alert rule sends new errors and business-critical failures (payments, refunds, stock) to a named person by email or message.
- [ ] An uptime monitor checks the readiness address every minute and alerts a person on two failures.
- [ ] A heartbeat for the nightly backup (section 2) alerts if it does not arrive.
- [ ] Cloudflare: the domain is proxied, SSL mode is full (strict), rate limits are set as in ADR 0002. Set `TRUST_CLOUDFLARE_HEADERS=1` only when the server accepts traffic from Cloudflare alone, as `base.py` says.
- [ ] The delivery of one alert is tested end to end, not assumed.

## 6. Go-live checklist (Week 6, from CLAUDE.md section 9)

Sign only after the restore drill and the device pass.
- [ ] CI green on `main`; staging deploys from a merge without a manual step
- [ ] Restore drill passed from the off-site copy (date: ____)
- [ ] Paystack test-mode run: webhook replayed three times, order paid once
- [ ] Delivery code issued, verified and locked after five wrong tries
- [ ] Order messages sent by SMS and email through the real providers
- [ ] Concurrency test: two buyers, last unit, exactly one succeeds
- [ ] Playwright: guest checkout, logged-in checkout, pay on delivery, delivery code
- [ ] Low-end Android on Chrome and iPhone on Safari checked
- [ ] Monitoring and alerts tested; backups scheduled and noticed when they fail
- [ ] Staff accounts have two-factor login
- [ ] No secrets in the repository, logs or fixtures
