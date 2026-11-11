# First deploy: from an empty server to a working HTTPS site

Status: written 9 November 2026. Needs no Cloudflare account and no Paystack key. The Caddy edge, the `.env` generator and the compose profiles were tested (see PRODUCTION-STACK.md). **Never run on a real server**: expect to fix a few things on the day.

You need: a server (Ubuntu 22.04 or 24.04) you can reach as root over SSH; a domain or subdomain you control; the repository (it is public, so no deploy key is needed).

Until the production stack is merged, use the branch `a/prod-stack-draft` wherever BRANCH appears below. After the merge, use `main`.

## 1. DNS (10 minutes, mostly waiting)
1. Create an **A record** for the name you chose (for example `staging.yourdomain.com`) pointing at the server's IP address.
2. If the DNS is on Cloudflare, set that record to **DNS only** (grey cloud). Certificates cannot be issued through the orange-cloud proxy in this setup.
3. Wait until `nslookup staging.yourdomain.com` (from your own computer) shows the server's IP.

## 2. Prepare the server (5 to 10 minutes)
As root on the server:
```
apt-get update && apt-get install -y git
git clone --depth 1 -b BRANCH https://github.com/Joetech-rgb/sk-clothing.git /tmp/skc
bash /tmp/skc/infra/server/bootstrap-ubuntu.sh
```
Open a **second** terminal and check you can log in as the new user (`ssh deploy@SERVER`) before closing the first. If you cannot, fix it while the root session is still open.

## 3. Get the code and write the settings
As the `deploy` user:
```
git clone -b BRANCH https://github.com/Joetech-rgb/sk-clothing.git ~/sk-clothing
cd ~/sk-clothing
bash infra/server/make-env.sh staging.yourdomain.com you@yourdomain.com
```
**Save the gate password it prints.** It is shown once. It protects `/admin/` (a prompt in front of Django's own login) and stands in for staff two-factor login, which does not exist yet.

Now edit `.env` (`nano .env`) and add the **public** Mapbox token (starts with `pk.`) as `NEXT_PUBLIC_MAPBOX_TOKEN`. It is built into the storefront, so add it before the first build. Leave `PAYSTACK_SECRET_KEY` empty for now.

## 4. Build and start (first build: 5 to 15 minutes)
```
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```
The profiles in `.env` choose what starts (Caddy and the storefront). To start the backend without the storefront, for example if its build fails: `COMPOSE_PROFILES=caddy docker compose -f docker-compose.prod.yml up -d --build`.

## 5. Create the database tables and your admin account
```
docker compose -f docker-compose.prod.yml run --rm backend python manage.py migrate
docker compose -f docker-compose.prod.yml run --rm backend python manage.py createsuperuser
```

## 6. Check it works
- `https://staging.yourdomain.com/api/v1/health/ready/` answers 200 (it checks the database and Redis). Certificates can take a minute on the first request.
- `https://staging.yourdomain.com/admin/` asks for the gate password, then shows Django's login.
- `https://staging.yourdomain.com/` shows the storefront.
- If something is wrong: `docker compose -f docker-compose.prod.yml logs --tail 80 caddy` (or `backend`, `storefront`).

## 7. Put data in (until the demo-data command exists)
In the admin: delivery settings (shop location, fees), stations, categories, then products with variants, tier prices and stock.

## 8. When the Paystack key arrives
1. Edit `.env`: `PAYSTACK_SECRET_KEY=sk_test_...` (the **test** key first).
2. `docker compose -f docker-compose.prod.yml up -d` (recreates the backend with the new key).
3. In the Paystack dashboard, set the webhook address to `https://staging.yourdomain.com/api/v1/payments/webhook/paystack/`.
Orders still become paid only after the server confirms with Paystack, so a missed webhook does not lose a payment.

## 9. Backups (do this on day one, 10 minutes)
See `docs/runbooks/OPERATIONS.md` section 2: a nightly `backup.sh` in cron, then one restore drill.

## Updating later
```
cd ~/sk-clothing && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm backend python manage.py migrate
```

## If something goes wrong
| Symptom | Likely cause and fix |
|---|---|
| No HTTPS certificate, browser warning | The name does not point at the server yet, ports 80 and 443 are blocked (check the provider's own firewall panel), or the DNS record is orange-cloud. Fix, then `docker compose -f docker-compose.prod.yml restart caddy` |
| Login or checkout says forbidden or "CSRF" | `CSRF_TRUSTED_ORIGINS` must be exactly `https://` plus the domain, no trailing slash, and `ALLOWED_HOSTS` must contain the domain. Edit `.env`, then `up -d` |
| Phone login says SMS unavailable | Expected until the Africa's Talking provider is built and configured. Guest checkout does not need SMS |
| Storefront shows 502 | The storefront is not running or still building: `docker compose -f docker-compose.prod.yml ps` and read its logs |
| Backend keeps restarting | Read `docker compose -f docker-compose.prod.yml logs backend`. A missing setting is named in the error |
| Admin asks for a password again and again | You are using the Django password at the gate prompt. The gate has its own password (printed by `make-env.sh`) |
