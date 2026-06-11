# 港漂安家 (HK Expats Rent)

A Simplified Chinese long-term rental lead-gen website for mainland Chinese students and expats relocating to Hong Kong.

- **Public site (port 5000)**: browse listings, filter by region / price / room type / nearby university, view full details with WeChat & WhatsApp contact CTAs. No auth surface.
- **Admin site (port 5001)**: password-protected listing manager, served by a **separate process**. Form uses sliders, segmented buttons, tag chips, and drag-drop image upload — designed for non-technical use.
- **Stack**: Python 3 + Flask + SQLite + Lightsail Object Storage. No JS frameworks, no CSS libraries.

The two processes share the SQLite DB and image storage but have zero shared URL
surface. In production they run as two systemd services on two ports / subdomains.

## Quick start (local dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env       # then edit ADMIN_PASSWORD and SECRET_KEY
python seed.py             # creates instance/data.db + admin user + 6 demo listings
```

Open **two terminals** — one for each process:

```bash
# Terminal 1 — public listings
python app.py public       # → http://localhost:5000

# Terminal 2 — admin / owner
python app.py admin        # → http://localhost:5001
```

The admin login uses `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`.

## Project layout

```
.
├── app.py                  create_public_app() + create_admin_app() factories
├── config.py               Loads .env via python-dotenv
├── db.py                   SQLite connection helper
├── schema.sql              CREATE TABLE statements
├── seed.py                 First-run setup (DB + admin + demo data)
├── auth.py                 Login / logout (admin process only)
├── storage.py              Image upload (local OR Lightsail Object Storage)
├── routes/
│   ├── public.py           public app: /, /house/<id>
│   └── admin.py            admin app: /, /houses/*, /upload
├── templates/
│   ├── base_public.html    Chrome for the public site (no auth nav)
│   ├── base_admin.html     Chrome for the admin site
│   ├── public/{index,detail}.html
│   └── admin/{login,dashboard,house_form}.html
├── static/
│   ├── css/{public.css, admin.css}
│   ├── js/admin.js
│   └── uploads/            (local image storage, gitignored)
├── design-reference/
│   └── index.html          Original English design demo (kept for visual reference)
└── instance/
    └── data.db             SQLite file (gitignored)
```

## Deployment

See [DEPLOY.md](DEPLOY.md) for the Lightsail setup walkthrough.
