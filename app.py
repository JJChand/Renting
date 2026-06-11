"""
The site runs as TWO isolated Flask apps that share the same SQLite DB and storage,
but are served on different ports / subdomains.

  • Public app  (port 5000)  → routes/public.py        — customer-facing listings
  • Admin app   (port 5001)  → routes/admin.py + auth  — owner / developer only

Why split: the public site has no auth surface at all (no /login route, no session
cookie, no admin blueprint). The admin lives behind a separate gunicorn process
that you can lock down at the firewall or expose on a different subdomain.

Dev usage:
    python app.py public      # → http://localhost:5000
    python app.py admin       # → http://localhost:5001
"""
import sys
from pathlib import Path

from flask import Flask
from flask_login import LoginManager

from config import Config
from db import close_db
from auth import load_user_by_id


def _common_init(app):
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["LOCAL_UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)


def create_public_app(config_class=Config):
    """Public listings site. No auth, no admin endpoints."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)
    _common_init(app)

    from routes.public import bp as public_bp
    app.register_blueprint(public_bp)
    return app


def create_admin_app(config_class=Config):
    """Owner / developer admin. Auth + house CRUD only."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)
    _common_init(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请先登录"
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load(user_id):
        return load_user_by_id(user_id)

    from auth import bp as auth_bp
    from routes.admin import bp as admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def _inject():
        return {"public_site_url": app.config["PUBLIC_SITE_URL"].rstrip("/")}

    return app


def _resolve(role):
    if role == "admin":
        return create_admin_app(), Config.ADMIN_PORT
    if role == "public":
        return create_public_app(), Config.PUBLIC_PORT
    raise SystemExit(f"Unknown role '{role}'. Use 'public' or 'admin'.")


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "public"
    app, port = _resolve(role)
    print(f"▶  Starting {role} app on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"])
