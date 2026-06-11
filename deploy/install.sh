#!/usr/bin/env bash
#
# Install systemd units + nginx server blocks for HK Expats Rent.
# Replaces the manual copy-paste in DEPLOY.md sections 5 and 6.
#
# Single-hostname mode: public on port 80, admin on port 8443.
# Compatible with free-tier dynamic DNS providers (NoIP, DuckDNS) that only
# give you one hostname.
#
# Usage (from anywhere):
#   sudo bash /opt/hk-expats-rent/deploy/install.sh <hostname>
#
# Example:
#   sudo bash deploy/install.sh gangpiao.ddns.net
#
# After this script:
#   - Both gunicorn services run as systemd daemons (auto-start on boot, auto-restart on crash)
#   - nginx serves the public site on port 80 and the admin on port 8443
#   - Both at the SAME hostname — different ports
#   - You still need to: open port 8443 in Lightsail firewall (see end of script output)
#
set -euo pipefail

# ---------- args ----------
if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <hostname>" >&2
    echo "Example: $0 gangpiao.ddns.net" >&2
    exit 1
fi
HOSTNAME_ARG="$1"

# ---------- must be root ----------
if [[ $EUID -ne 0 ]]; then
    echo "✗ This script must run as root. Re-run with: sudo bash $0 $*" >&2
    exit 1
fi

# ---------- resolve paths ----------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
RUN_USER="${SUDO_USER:-ubuntu}"
PUBLIC_PORT="8000"        # gunicorn loopback port for public
ADMIN_PORT="8001"         # gunicorn loopback port for admin
ADMIN_HTTP_PORT="8443"    # external port nginx exposes admin on

# ---------- preflight ----------
echo "▶  Preflight checks"
[[ -d "$PROJECT_ROOT/.venv" ]]   || { echo "✗ Missing $PROJECT_ROOT/.venv — run 'python3 -m venv .venv && .venv/bin/pip install -r requirements.txt' first"; exit 1; }
[[ -f "$PROJECT_ROOT/app.py" ]]  || { echo "✗ $PROJECT_ROOT/app.py not found — is this the project root?"; exit 1; }
[[ -f "$PROJECT_ROOT/.env" ]]    || { echo "✗ Missing $PROJECT_ROOT/.env — copy .env.example to .env and fill it in first"; exit 1; }
command -v nginx >/dev/null      || { echo "✗ nginx not installed — run 'sudo apt install nginx' first"; exit 1; }
command -v systemctl >/dev/null  || { echo "✗ systemctl not available (this script targets systemd-based Linux)"; exit 1; }
id "$RUN_USER" >/dev/null 2>&1   || { echo "✗ User '$RUN_USER' does not exist"; exit 1; }

echo "    ✓ project at:       $PROJECT_ROOT"
echo "    ✓ run as user:      $RUN_USER"
echo "    ✓ hostname:         $HOSTNAME_ARG"
echo "    ✓ public:           http://$HOSTNAME_ARG/           (nginx :80   → gunicorn :$PUBLIC_PORT)"
echo "    ✓ admin:            http://$HOSTNAME_ARG:$ADMIN_HTTP_PORT/   (nginx :$ADMIN_HTTP_PORT → gunicorn :$ADMIN_PORT)"
echo

# ---------- confirm ----------
read -r -p "Proceed with install? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ---------- helper: substitute template vars ----------
render() {
    local src="$1" dst="$2"
    sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        -e "s|{{RUN_USER}}|$RUN_USER|g" \
        -e "s|{{HOSTNAME}}|$HOSTNAME_ARG|g" \
        -e "s|{{PUBLIC_PORT}}|$PUBLIC_PORT|g" \
        -e "s|{{ADMIN_PORT}}|$ADMIN_PORT|g" \
        -e "s|{{ADMIN_HTTP_PORT}}|$ADMIN_HTTP_PORT|g" \
        "$src" > "$dst"
}

# ---------- ensure runtime dirs exist with correct ownership ----------
echo "▶  Ensuring runtime directories exist"
install -d -o "$RUN_USER" -g "$RUN_USER" "$PROJECT_ROOT/instance"
install -d -o "$RUN_USER" -g "$RUN_USER" "$PROJECT_ROOT/static/uploads"

# ---------- systemd units (DEPLOY.md §5) ----------
echo "▶  Installing systemd units"
render "$SCRIPT_DIR/hk-rent-public.service.template" /etc/systemd/system/hk-rent-public.service
render "$SCRIPT_DIR/hk-rent-admin.service.template"  /etc/systemd/system/hk-rent-admin.service
chmod 644 /etc/systemd/system/hk-rent-public.service /etc/systemd/system/hk-rent-admin.service

systemctl daemon-reload
systemctl enable --now hk-rent-public hk-rent-admin

sleep 2
for svc in hk-rent-public hk-rent-admin; do
    if systemctl is-active --quiet "$svc"; then
        echo "    ✓ $svc is running"
    else
        echo "    ✗ $svc failed to start — check 'journalctl -u $svc -n 50'"
        exit 1
    fi
done

# ---------- nginx (DEPLOY.md §6) ----------
echo "▶  Installing nginx server blocks"
render "$SCRIPT_DIR/nginx-public.conf.template" /etc/nginx/sites-available/hk-rent-public
render "$SCRIPT_DIR/nginx-admin.conf.template"  /etc/nginx/sites-available/hk-rent-admin
chmod 644 /etc/nginx/sites-available/hk-rent-public /etc/nginx/sites-available/hk-rent-admin

ln -sf /etc/nginx/sites-available/hk-rent-public /etc/nginx/sites-enabled/hk-rent-public
ln -sf /etc/nginx/sites-available/hk-rent-admin  /etc/nginx/sites-enabled/hk-rent-admin
rm -f /etc/nginx/sites-enabled/default

echo "▶  Validating nginx config"
nginx -t

echo "▶  Reloading nginx"
systemctl reload nginx

# ---------- smoke test ----------
echo "▶  Smoke testing local endpoints"
sleep 1
pub_status=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PUBLIC_PORT/" || true)
adm_status=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$ADMIN_PORT/" || true)
nginx_pub=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: $HOSTNAME_ARG" "http://127.0.0.1/" || true)
nginx_adm=$(curl -s -o /dev/null -w "%{http_code}" -H "Host: $HOSTNAME_ARG" "http://127.0.0.1:$ADMIN_HTTP_PORT/" || true)
[[ "$pub_status" == "200" ]] && echo "    ✓ gunicorn public  127.0.0.1:$PUBLIC_PORT/ → 200"           || echo "    ⚠ gunicorn public  → $pub_status (expected 200)"
[[ "$adm_status" == "302" ]] && echo "    ✓ gunicorn admin   127.0.0.1:$ADMIN_PORT/ → 302"            || echo "    ⚠ gunicorn admin   → $adm_status (expected 302)"
[[ "$nginx_pub" == "200" ]]  && echo "    ✓ nginx → public   :80   → 200"                              || echo "    ⚠ nginx public     → $nginx_pub (expected 200)"
[[ "$nginx_adm" == "302" ]]  && echo "    ✓ nginx → admin    :$ADMIN_HTTP_PORT → 302 (redirects to /login)" || echo "    ⚠ nginx admin      → $nginx_adm (expected 302)"

cat <<EOF

✅  Install complete.

Public URL:  http://$HOSTNAME_ARG/
Admin URL:   http://$HOSTNAME_ARG:$ADMIN_HTTP_PORT/

Next steps:
  1. Point your NoIP / DuckDNS hostname at this Lightsail instance's static IP
     (you only need ONE hostname — admin reuses the same one on a different port).

  2. Open port $ADMIN_HTTP_PORT in the Lightsail firewall:
        Application: Custom
        Protocol:    TCP
        Port:        $ADMIN_HTTP_PORT
        Source:      Your laptop's IP only (run \`curl ifconfig.me\` on your Mac)
     You can also CLOSE the temporary 8000 / 8001 rules now — nginx is the front door.

  3. Update .env to use the hostname (no port for public, since nginx is on :80):
        PUBLIC_SITE_URL=http://$HOSTNAME_ARG
     Then restart the public service:
        sudo systemctl restart hk-rent-public

  4. Verify from your laptop browser:
        http://$HOSTNAME_ARG/                  → public listings
        http://$HOSTNAME_ARG:$ADMIN_HTTP_PORT/ → admin login

This script is idempotent — safe to re-run after a code update or config change.
EOF
