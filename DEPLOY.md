# Deploying to AWS Lightsail

The site runs as **two isolated processes** that share the same SQLite database and
image storage but are served on different ports:

| Process | gunicorn (loopback) | External URL                       | Purpose                          |
|---------|---------------------|------------------------------------|----------------------------------|
| Public  | 127.0.0.1:8000      | `http://your-host/`                | Customer-facing listings, no auth |
| Admin   | 127.0.0.1:8001      | `http://your-host:8443/`           | Owner / dev login + house CRUD    |

Why split: the public site has zero auth surface (no `/login`, no session cookie,
no admin endpoints). The admin runs as a separate gunicorn process on a separate
external port that you can lock down at the firewall.

**Single-hostname design** — public on port 80, admin on port 8443, **same hostname**.
This works with free-tier dynamic DNS (NoIP, DuckDNS) that only gives you one
hostname, and keeps the process isolation intact.

Stack: Ubuntu + gunicorn + systemd + nginx + Let's Encrypt (optional).
Estimated monthly cost: **~$5** ($5 instance, local image storage on the SSD).

---

## 1. Create the Lightsail instance

1. Lightsail console → **Create instance**
2. **Region**: a region close to your users (Singapore `ap-southeast-1` works well for mainland China traffic)
3. Blueprint: **OS Only → Ubuntu 22.04 LTS**
4. Plan: **$5/month** (1 GB RAM, 40 GB SSD)
5. Name it `hk-expats-rent` → create
6. Attach a **static IP** (free while attached)

SSH in:

```bash
chmod 600 ~/Downloads/LightsailDefaultKey-<region>.pem
ssh -i ~/Downloads/LightsailDefaultKey-<region>.pem ubuntu@<static-ip>
```

## 2. Point a hostname at the instance

Any DNS provider works. For a free option:

1. Create an account at https://www.noip.com
2. Add a hostname (e.g. `gangpiao.ddns.net`)
3. Point it at your Lightsail static IP
4. Verify from your laptop:
   ```bash
   dig gangpiao.ddns.net
   ```
   The answer section should show your Lightsail IP.

A paid `.com` domain (~$10/yr from Cloudflare or Namecheap) works exactly the same way — just add an A record pointing at the static IP.

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
# Generate a SECRET_KEY with:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
# Paste the OUTPUT below (not the command itself).
SECRET_KEY=<paste-the-64-char-hex-output>
FLASK_DEBUG=false

PUBLIC_PORT=8000
ADMIN_PORT=8001
PUBLIC_SITE_URL=http://gangpiao.ddns.net

ADMIN_USERNAME=admin
ADMIN_PASSWORD=<a-strong-password>

STORAGE_BACKEND=local
LOCAL_UPLOAD_DIR=static/uploads
LOCAL_UPLOAD_URL_PREFIX=/static/uploads
```

Initialize the database:

```bash
.venv/bin/python seed.py
```

## 5–6. Install systemd + nginx (one command)

```bash
sudo bash deploy/install.sh gangpiao.ddns.net
```

That single command does sections 5 and 6 below:

- Substitutes your hostname and `$PROJECT_ROOT` into the templates in `deploy/*.template`
- Writes the two systemd unit files and `daemon-reload + enable --now`s them
- Writes the two nginx server blocks (public on `:80`, admin on `:8443`, both for your hostname)
- Symlinks them into `sites-enabled/`, removes the default
- Runs `nginx -t` and reloads nginx
- Smoke-tests all four endpoints (gunicorn loopback + nginx external)

The script is idempotent — re-run it any time the templates change or after you swap hostnames.

After it finishes:

1. **Open port 8443 in the Lightsail firewall**, restricted to your laptop's IP
   (run `curl ifconfig.me` on your Mac to find it):

   | Application | Protocol | Port | Source |
   |---|---|---|---|
   | Custom | TCP | 8443 | Your IP only |

   You can also **delete** the temporary 8000 / 8001 rules from the smoke-test
   stage — nginx is now the front door.

2. Visit from your laptop:
   - Public: `http://gangpiao.ddns.net/`
   - Admin: `http://gangpiao.ddns.net:8443/` → log in with `.env` credentials

If you want to see what the script does or run sections 5 and 6 by hand, both
follow — but you can safely skip to section 7.

---

## 5. Two systemd services (manual reference)

Each process gets its own systemd unit. Templates in `deploy/*.service.template`,
or pre-substituted versions below.

### 5a. Public service — `/etc/systemd/system/hk-rent-public.service`

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

### 5b. Admin service — `/etc/systemd/system/hk-rent-admin.service`

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

## 6. nginx — two server blocks (manual reference)

### 6a. Public — `/etc/nginx/sites-available/hk-rent-public`

```nginx
server {
    listen 80;
    server_name gangpiao.ddns.net;

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

### 6b. Admin — `/etc/nginx/sites-available/hk-rent-admin`

Same hostname, different port. nginx distinguishes the two apps by which port
the request hits.

```nginx
server {
    listen 8443;
    server_name gangpiao.ddns.net;

    client_max_body_size 20M;              # allow image uploads

    # Recommended: restrict admin to your home/office IP.
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

## 7. HTTPS (strongly recommended, especially if the admin is open to "Any IPv4")

Use **`certonly --standalone`** to get a cert, then re-run `install.sh` — it
auto-detects the cert and switches to HTTPS-mode nginx configs (port 80 redirects
to 443, public on 443 ssl, admin on 8443 ssl, one shared cert).

> **Why not `certbot --nginx`?** The `--nginx` plugin scans configs for matching
> `server_name` and edits the first one it finds — in this single-hostname setup
> it accidentally adds `listen 443 ssl` to the **admin** block, breaking the
> public site. `certonly --standalone` only issues the cert and lets the
> templates do the wiring.

```bash
# 1. Stop nginx briefly so certbot's standalone can use port 80
sudo systemctl stop nginx

# 2. Issue the cert
sudo certbot certonly --standalone -d ganghouse.cc -d www.ganghouse.cc

# 3. Start nginx and re-run install.sh (it detects the cert, picks HTTPS templates)
sudo systemctl start nginx
sudo bash deploy/install.sh ganghouse.cc

# 4. Update .env and reload Flask services
sed -i 's|^PUBLIC_SITE_URL=.*|PUBLIC_SITE_URL=https://ganghouse.cc|' .env
sudo systemctl restart hk-rent-public hk-rent-admin
```

After this:

- `http://ganghouse.cc/`         → 301 redirect to `https://ganghouse.cc/`
- `https://ganghouse.cc/`        → public listings (cert valid)
- `https://ganghouse.cc:8443/`   → admin login (same cert)

Auto-renewal: certbot installs a systemd timer that renews on its own; the renewed
cert files keep the same paths the nginx configs reference, so nothing else is needed.

## 8. Locking down the admin

Defense in depth — pick any combination:

- **Lightsail firewall** — restrict port 8443 to **your laptop's IP only** (the firewall is the cheapest filter and stops the brute-force scan traffic).
- **nginx allow/deny** — uncomment the `allow` / `deny` snippet in `hk-rent-admin` for your IP. Catches anyone who slips past the firewall.
- **Strong password + login rate limit**. Add to the admin server block:
  ```nginx
  limit_req_zone $binary_remote_addr zone=admin_login:10m rate=5r/m;
  location = /login {
      limit_req zone=admin_login burst=3 nodelay;
      proxy_pass http://127.0.0.1:8001;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
  }
  ```
- **Don't link to the admin from anywhere public** — `noindex, nofollow` is already
  set in the admin layout, but obscurity helps too.

The admin gunicorn binds to `127.0.0.1:8001`, never `0.0.0.0`, so port 8001 itself
is never reachable from the internet — only nginx (`:80`, `:8443`) is.

## 9. Verify

- `http://gangpiao.ddns.net/` → public listings, no admin links anywhere
- `http://gangpiao.ddns.net:8443/` → admin login page
- Log in, create a listing with one or more images → confirm:
  - images load at URLs starting with `/static/uploads/houses/...`
  - the dashboard's "查看 ↗" link opens the public site (port 80) in a new tab and shows the new listing

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

**Back up the database AND images** (nightly cron, 3 AM):

```cron
0 3 * * * tar czf /opt/hk-expats-rent/instance/backup-$(date +\%Y\%m\%d).tar.gz \
              /opt/hk-expats-rent/instance/data.db \
              /opt/hk-expats-rent/static/uploads
```

For off-instance safety, `scp` or `rsync` that tarball to your laptop on a
schedule, or pay $1/mo for Lightsail snapshots.

**View logs:**

```bash
sudo journalctl -u hk-rent-public -f
sudo journalctl -u hk-rent-admin -f
sudo tail -f /var/log/nginx/access.log
```

**Reset the admin password:** edit `ADMIN_PASSWORD` in `.env`, then re-run
`.venv/bin/python seed.py` (it updates the user without touching listings),
then `sudo systemctl restart hk-rent-admin`.

**Re-run install.sh after changing hostname:** safe — overwrites systemd units,
nginx configs, re-enables everything. Just remember to also update `.env`
(`PUBLIC_SITE_URL`) and reload `hk-rent-public`.
