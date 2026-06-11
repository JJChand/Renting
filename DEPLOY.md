# Deploying to AWS Lightsail

The site runs as **two isolated processes** that share the same SQLite database and
image storage but are served on different ports / subdomains:

| Process | Port (internal) | Public URL                  | Purpose                          |
|---------|-----------------|------------------------------|----------------------------------|
| Public  | 8000            | https://your-domain.com       | Customer-facing listings, no auth |
| Admin   | 8001            | https://admin.your-domain.com | Owner / dev login + house CRUD    |

Why split: the public site has zero auth surface (no `/login`, no session cookie,
no admin endpoints). The admin runs as a separate gunicorn process you can lock
down at the firewall or hide on a private subdomain.

Stack: Ubuntu + gunicorn + systemd + nginx + Let's Encrypt.
Estimated monthly cost: **~$6** ($5 instance + $1 object storage).

---

## 1. Create the Lightsail instance

1. Lightsail console → **Create instance**
2. **Region**: Asia Pacific (Hong Kong) `ap-east-1` for low latency to your audience
3. Blueprint: **OS Only → Ubuntu 22.04 LTS**
4. Plan: **$5/month** (1 GB RAM, 40 GB SSD)
5. Name it `hk-expats-rent` → create
6. **Networking**: open ports `80` and `443`
7. Attach a **static IP** (free while attached)

SSH in:

```bash
ssh -i ~/Downloads/LightsailDefaultKey-ap-east-1.pem ubuntu@<static-ip>
```

## 2. Create the Object Storage bucket

1. Lightsail console → **Object storage → Create bucket**
2. Same region as your instance (Hong Kong)
3. Name: `hk-expats-rent` (globally unique — try a suffix if taken)
4. Plan: **$1/month** (25 GB)
5. After creation: **Object access** → **Public (read-only)**
6. **Manage access keys** → create + copy the keys for `.env` later

## 3. Install system packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nginx git certbot python3-certbot-nginx
```

## 4. Deploy the application

```bash
sudo mkdir -p /opt/hk-expats-rent
sudo chown ubuntu:ubuntu /opt/hk-expats-rent
cd /opt/hk-expats-rent

git clone <your-repo-url> .
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env
```

Fill in `.env` for production:

```bash
SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
FLASK_DEBUG=false

PUBLIC_PORT=8000
ADMIN_PORT=8001
PUBLIC_SITE_URL=https://your-domain.com

ADMIN_USERNAME=admin
ADMIN_PASSWORD=<a-strong-password>

STORAGE_BACKEND=s3
S3_BUCKET=hk-expats-rent
S3_REGION=ap-east-1
S3_ENDPOINT_URL=https://s3.ap-east-1.amazonaws.com
S3_ACCESS_KEY=<from step 2>
S3_SECRET_KEY=<from step 2>
S3_PUBLIC_URL_BASE=https://hk-expats-rent.s3.ap-east-1.amazonaws.com
```

Initialize the database:

```bash
.venv/bin/python seed.py
```

## 5–6. Automated install (recommended)

Sections 5 and 6 below show the manual steps for systemd + nginx. To run them in
one shot, use the bundled script:

```bash
sudo bash deploy/install.sh your-domain.com admin.your-domain.com
```

It:
- Substitutes your domains and `$PROJECT_ROOT` into the templates in `deploy/*.template`
- Writes the two systemd unit files and `daemon-reload + enable --now`s them
- Writes the two nginx server blocks, symlinks them into `sites-enabled/`, removes the default
- Runs `nginx -t` and reloads nginx
- Smoke-tests both gunicorn processes on their loopback ports

After it finishes, **skip to section 7 (DNS + HTTPS)**. The script is idempotent —
safe to re-run after code changes.

If you want to see what it does or do it by hand, the manual steps follow.

---

## 5. Two systemd services (one per process)

### 5a. Public service

Create `/etc/systemd/system/hk-rent-public.service`:

```ini
[Unit]
Description=HK Expats Rent — Public site (gunicorn)
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/hk-expats-rent
Environment="PATH=/opt/hk-expats-rent/.venv/bin"
ExecStart=/opt/hk-expats-rent/.venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    --access-logfile - \
    "app:create_public_app()"
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 5b. Admin service

Create `/etc/systemd/system/hk-rent-admin.service`:

```ini
[Unit]
Description=HK Expats Rent — Admin site (gunicorn)
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/hk-expats-rent
Environment="PATH=/opt/hk-expats-rent/.venv/bin"
ExecStart=/opt/hk-expats-rent/.venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:8001 \
    --access-logfile - \
    "app:create_admin_app()"
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable both:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hk-rent-public hk-rent-admin
sudo systemctl status hk-rent-public hk-rent-admin

curl -I http://127.0.0.1:8000/         # public — 200 expected
curl -I http://127.0.0.1:8001/         # admin  — 302 expected (redirect to /login)
```

## 6. nginx — two server blocks

### 6a. Public site

Create `/etc/nginx/sites-available/hk-rent-public`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location /static/ {
        alias /opt/hk-expats-rent/static/;
        expires 7d;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 6b. Admin site

Create `/etc/nginx/sites-available/hk-rent-admin`:

```nginx
server {
    listen 80;
    server_name admin.your-domain.com;

    client_max_body_size 20M;              # allow image uploads

    # Recommended: restrict admin to your office/home IP.
    # Get your current IP from https://ifconfig.me — replace below.
    # allow 203.0.113.42;
    # deny  all;

    location /static/ {
        alias /opt/hk-expats-rent/static/;
        expires 7d;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable both, drop the default:

```bash
sudo ln -s /etc/nginx/sites-available/hk-rent-public /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/hk-rent-admin  /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## 7. DNS + HTTPS

1. In your DNS provider, add **two A records** pointing to the Lightsail static IP:
   - `your-domain.com`         → `<static-ip>`
   - `admin.your-domain.com`   → `<static-ip>`

2. Wait for DNS to propagate (`dig admin.your-domain.com` should return the IP)

3. Run certbot for both domains:

```bash
sudo certbot --nginx \
    -d your-domain.com -d www.your-domain.com \
    -d admin.your-domain.com
```

Certbot edits both nginx server blocks to add HTTPS and sets up auto-renewal.

## 8. Locking down the admin (recommended)

The admin URL is now publicly resolvable, even on a separate subdomain. Pick ONE
or more of these to reduce attack surface:

- **IP allowlist in nginx** — uncomment the `allow` / `deny` lines in
  `hk-rent-admin` for your home/office IP. Update when your IP changes.
- **Don't publish the admin subdomain anywhere** — no public links to it, no
  sitemap entry, no mention. The `noindex, nofollow` meta tag is already set in
  the admin layout.
- **Strong password + rate limiting**. To rate-limit logins, add to the admin
  server block:
  ```nginx
  limit_req_zone $binary_remote_addr zone=admin_login:10m rate=5r/m;
  location = /login { limit_req zone=admin_login burst=3 nodelay; proxy_pass http://127.0.0.1:8001; ... }
  ```
- **Don't expose the admin port directly** — only nginx (80/443) should be
  reachable from the public internet. Port 8001 stays bound to `127.0.0.1`, which
  the systemd unit above already does.

## 9. Verify

- `https://your-domain.com` → public listings, no admin links anywhere
- `https://admin.your-domain.com` → admin login page
- Log in, create a listing with images → confirm:
  - images live at `https://hk-expats-rent.s3.ap-east-1.amazonaws.com/...`
  - the dashboard's "查看 ↗" link opens the public site in a new tab and shows the new listing

## Day-2 operations

**Deploy a code change:**

```bash
cd /opt/hk-expats-rent
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart hk-rent-public hk-rent-admin
```

**Restart just one process** (e.g. after an admin-only change):

```bash
sudo systemctl restart hk-rent-admin
```

**Back up the database** (nightly cron, 3 AM):

```cron
0 3 * * * cp /opt/hk-expats-rent/instance/data.db /opt/hk-expats-rent/instance/data.db.bak.$(date +\%Y\%m\%d)
```

For off-instance backups, install AWS CLI and `aws s3 cp` to your object storage bucket.

**View logs:**

```bash
sudo journalctl -u hk-rent-public -f
sudo journalctl -u hk-rent-admin -f
sudo tail -f /var/log/nginx/access.log
```

**Reset the admin password:** edit `ADMIN_PASSWORD` in `.env`, then re-run
`.venv/bin/python seed.py` (it updates the user without touching listings),
then `sudo systemctl restart hk-rent-admin`.
