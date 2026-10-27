#!/usr/bin/env bash
# OBOR server setup for Ubuntu — installs backend + Cloudflare quick tunnel
# as systemd services (start on boot, auto-restart on crash).
#
# Usage (on the Ubuntu server):
#   curl -fsSL https://raw.githubusercontent.com/zulganzs/obor/main/scripts/server/setup.sh -o setup.sh
#   sudo bash setup.sh
#
# Re-runnable (idempotent). NOTE: each re-run restarts the tunnel, which
# rotates the random *.trycloudflare.com URL — paste the new URL printed
# at the end to whoever manages netlify.toml.
#
# Stable-URL upgrade path (if you own a domain): see the note this script
# prints at the end, or ask for the named-tunnel variant.

set -euo pipefail

# Private backend repo (SSH + deploy key). Netlify's public fork is
# intentionally separate and stays the dashboard source.
REPO_URL="git@github.com:zulganzs/obooor.git"
SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# run from inside a clone → use that clone; standalone → fresh clone to ~/obor
if git -C "$SCRIPT_DIR/.." rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    APP_DIR="$SERVICE_HOME/obor"
fi

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run with sudo: sudo bash setup.sh"; exit 1; }

echo "=========================================================="
echo "  OBOR server setup — user: $SERVICE_USER  dir: $APP_DIR"
echo "=========================================================="

# ── 1. System packages ──────────────────────────────────────────
echo ">>> [1/6] apt packages"
# tolerate partial repo failures (broken/third-party sources like cPanel's
# don't provide anything we need; main Ubuntu repos are what matter)
apt-get update -qq || echo "  (apt update warnings ignored — system packages unaffected)"
apt-get install -y -qq python3 python3-venv git curl >/dev/null

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "ERROR: Python >= 3.10 required (found $(python3 --version)). Ubuntu 22.04+ recommended."; exit 1;
}

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)        CF_ARCH="amd64" ;;
    aarch64|arm64) CF_ARCH="arm64" ;;
    *)             echo "ERROR: unsupported architecture: $ARCH"; exit 1 ;;
esac

# ── 2. Application code ──────────────────────────────────────────
echo ">>> [2/6] fetching code"
# github.com SSH via port 443 (common ISP port-22 blocks; harmless when unblocked)
SSHCFG="$SERVICE_HOME/.ssh/config"
sudo -u "$SERVICE_USER" mkdir -p "$SERVICE_HOME/.ssh"
if ! sudo -u "$SERVICE_USER" grep -q "ssh.github.com" "$SSHCFG" 2>/dev/null; then
    printf 'Host github.com\n  HostName ssh.github.com\n  Port 443\n  User git\n  StrictHostKeyChecking accept-new\n' >> "$SSHCFG"
    chown "$SERVICE_USER" "$SSHCFG"
    chmod 600 "$SSHCFG"
fi
if [ -d "$APP_DIR/.git" ]; then
    sudo -u "$SERVICE_USER" git -C "$APP_DIR" pull --ff-only || echo "  (git pull failed — continuing with existing code)"
else
    sudo -u "$SERVICE_USER" git clone -q "$REPO_URL" "$APP_DIR"
fi

# ── 3. Python environment ───────────────────────────────────────
echo ">>> [3/6] python venv + ML dependencies (~200MB, may take a few minutes)"
if [ ! -x "$APP_DIR/.venv/bin/pip" ]; then
    sudo -u "$SERVICE_USER" python3 -m venv "$APP_DIR/.venv"
fi
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$APP_DIR/requirements.txt"

AVAILABLE_KB=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
[ "$AVAILABLE_KB" -lt 900 ] && echo "  WARNING: only ${AVAILABLE_KB}MB RAM free — ML imports need ~700MB; app may OOM."

# ── 4. Backend systemd service ──────────────────────────────────
echo ">>> [4/6] obor-backend service"
cat > /etc/systemd/system/obor-backend.service <<EOF
[Unit]
Description=OBOR wildfire backend
After=network.target

[Service]
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment=DEMO_MODE=true
Environment=PORT=8000
ExecStart=$APP_DIR/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable obor-backend >/dev/null 2>&1
systemctl restart obor-backend

echo "  waiting for backend..."
HEALTH=""
for _ in $(seq 1 30); do
    if curl -s -m 3 http://localhost:8000/health | grep -q '"status":"healthy"'; then HEALTH="ok"; break; fi
    sleep 2
done
[ -n "$HEALTH" ] || { echo "ERROR: backend did not become healthy. Check: journalctl -u obor-backend -b --no-pager | tail -40"; exit 1; }
echo "  backend healthy on :8000"

# ── 5. cloudflared ──────────────────────────────────────────────
echo ">>> [5/6] cloudflared ($CF_ARCH)"
if ! [ -x /usr/local/bin/cloudflared ]; then
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" \
        -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
fi

# ── 6. Tunnel systemd service ────────────────────────────────────
echo ">>> [6/6] obor-tunnel service"
cat > /etc/systemd/system/obor-tunnel.service <<EOF
[Unit]
Description=OBOR Cloudflare quick tunnel
Wants=network-online.target
After=network-online.target obor-backend.service

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8000 --no-autoupdate
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable obor-tunnel >/dev/null 2>&1
systemctl restart obor-tunnel

echo "  waiting for tunnel URL..."
URL=""
for _ in $(seq 1 20); do
    URL=$(journalctl -u obor-tunnel --since "3 minutes ago" -o cat 2>/dev/null \
        | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)
    [ -n "$URL" ] && break
    sleep 3
done
[ -n "$URL" ] || { echo "ERROR: tunnel did not produce a URL. Check: journalctl -u obor-tunnel -b --no-pager | tail -40"; exit 1; }
PUBLIC_URL_TEST=$(curl -s -m 15 -o /dev/null -w "%{http_code}" "$URL/health" || echo fail)
[ "$PUBLIC_URL_TEST" = "200" ] || echo "  NOTE: tunnel URL returned $PUBLIC_URL_TEST on first probe — may still be warming up."

echo ""
echo "=========================================================="
echo "  SETUP COMPLETE ✅"
echo "=========================================================="
echo "  Public backend URL:  $URL"
echo "  Verify:              $URL/health"
echo ""
echo "  Your Netlify dashboard proxy should point at the URL above."
echo ""
echo "  Useful commands:"
echo "    systemctl status obor-backend obor-tunnel"
echo "    journalctl -u obor-backend -f        # follow backend logs"
echo "    journalctl -u obor-tunnel -b | grep trycloudflare   # re-find URL after reboot"
echo ""
echo "  NOTE: the quick-tunnel URL rotates on every restart/reboot."
echo "  After a reboot, re-run the grep above and update netlify.toml,"
echo "  or ask for the named-tunnel variant (needs a domain, gives a"
echo "  permanent obor.YOURDOMAIN.com URL)."
echo "=========================================================="
