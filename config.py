import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-DO-NOT-USE-IN-PROD")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    DATABASE_PATH = str(BASE_DIR / os.environ.get("DATABASE_PATH", "instance/data.db"))

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()

    LOCAL_UPLOAD_DIR = str(BASE_DIR / os.environ.get("LOCAL_UPLOAD_DIR", "static/uploads"))
    LOCAL_UPLOAD_URL_PREFIX = os.environ.get("LOCAL_UPLOAD_URL_PREFIX", "/static/uploads")

    S3_BUCKET = os.environ.get("S3_BUCKET", "")
    S3_REGION = os.environ.get("S3_REGION", "ap-southeast-1")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
    S3_PUBLIC_URL_BASE = os.environ.get("S3_PUBLIC_URL_BASE", "")

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

    # Two-process split: public listings on one port, admin on another.
    PUBLIC_PORT = int(os.environ.get("PUBLIC_PORT", "5000"))
    ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "5001"))
    # Used by the admin app to render "view on public site" links across the port boundary.
    PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", f"http://localhost:{PUBLIC_PORT}")
