#!/usr/bin/env bash
#
# Install systemd units + nginx server blocks for HK Expats Rent.
# Replaces the manual copy-paste in DEPLOY.md sections 5 and 6.
#
# Usage (from anywhere):
#   sudo bash /opt/hk-expats-rent/deploy/install.sh <public-domain> <admin-domain>
#
# Example:
#   sudo bash deploy/install.sh gangpiao-anjia.com admin.gangpiao-anjia.com
#
# After this script:
#   - Both gunicorn services are running on 127.0.0.1:8000 / :8001
#   - nginx serves them on port 80 for the two domains
#   - You still need to: point DNS at this host, then run certbot (see DEPLOY.md §7)
#
set -euo pipefail

# ---------- args ----------
if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <public-domain> <admin-domain>" >&2
    echo "Example: $0 gangpiao-anjia.com admin.gangpiao-anjia.com" >&2
    exit 1
fi
PUBLIC_DOMAIN="$1"
ADMIN_DOMAIN="$2"

# ---------- must be root ----------
if [[ $EUID -ne 0 ]]; then
    echo "✗ This script must run as root. Re-run with: sudo bash $0 $*" >&2
    exit 1
fi

# ---------- resolve paths ----------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
RUN_USER="${SUDO_USER:-ubuntu}"           # the non-root user that owns the project
PUBLIC_PORT="8000"
ADMIN_PORT="8001"

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
echo "    ✓ public domain:    $PUBLIC_DOMAIN  (gunicorn on :$PUBLIC_PORT)"
echo "    ✓ admin domain:     $ADMIN_DOMAIN  (gunicorn on :$ADMIN_PORT)"
echo

# ---------- confirm ----------
read -r -p "Proceed with install? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ---------- helper: substitute template vars ----------
render() {
    local src="$1" dst="$2"
    sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        -e "s|{{RUN_USER}}|$RUN_USER|g" \
        -e "s|{{PUBLIC_DOMAIN}}|$PUBLIC_DOMAIN|g" \
        -e "s|{{ADMIN_DOMAIN}}|$ADMIN_DOMAIN|g" \
        -e "s|{{PUBLIC_PORT}}|$PUBLIC_PORT|g" \
        -e "s|{{ADMIN_PORT}}|$ADMIN_PORT|g" \
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

# Give them a moment, then check status
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
[[ "$pub_status" == "200" ]] && echo "    ✓ public  127.0.0.1:$PUBLIC_PORT/ → 200" || echo "    ⚠ public  127.0.0.1:$PUBLIC_PORT/ → $pub_status (expected 200)"
[[ "$adm_status" == "302" ]] && echo "    ✓ admin   127.0.0.1:$ADMIN_PORT/ → 302 (redirects to /login)" || echo "    ⚠ admin   127.0.0.1:$ADMIN_PORT/ → $adm_status (expected 302)"

cat <<EOF

✅  Install complete.

Next steps (DEPLOY.md §7):
  1. Point DNS A records at this host:
        $PUBLIC_DOMAIN          → <this-host-public-ip>
        www.$PUBLIC_DOMAIN      → <this-host-public-ip>
        $ADMIN_DOMAIN           → <this-host-public-ip>
  2. Wait for DNS to propagate (check with: dig $ADMIN_DOMAIN)
  3. Run certbot to issue HTTPS certs:
        sudo certbot --nginx -d $PUBLIC_DOMAIN -d www.$PUBLIC_DOMAIN -d $ADMIN_DOMAIN

To rerun this script later (e.g. after a code update), the existing services and
configs will simply be overwritten — it is safe to run again.
EOF
