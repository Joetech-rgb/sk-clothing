#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu server. Run as root:   bash bootstrap-ubuntu.sh
# Installs Docker, git and a firewall, creates a "deploy" user, and opens only SSH, HTTP, HTTPS.
# NOT tested on a real server: read the output, and keep your current SSH session open until you have
# logged in again as the deploy user in a second window.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root." >&2
  exit 1
fi
DEPLOY_USER="${DEPLOY_USER:-deploy}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl git ufw

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "The docker compose plugin is missing. Install docker-compose-plugin and run this again." >&2
  exit 1
fi
systemctl enable --now docker

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
# The same SSH key that logs in as root may log in as the deploy user.
if [ -f /root/.ssh/authorized_keys ]; then
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
  install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /root/.ssh/authorized_keys \
    "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi

# Docker publishes ports around ufw, so what really protects the database and Redis is that the
# compose file never publishes them. Only ports 80 and 443 are published.
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo
echo "Done. Docker: $(docker --version)"
echo "Next, in a NEW window, check you can log in as $DEPLOY_USER before closing this one:"
echo "  ssh $DEPLOY_USER@<this server>"
