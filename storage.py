"""
Image storage layer.

Two backends, toggled via STORAGE_BACKEND in .env:
  - "local"  → saves to LOCAL_UPLOAD_DIR, served by Flask at LOCAL_UPLOAD_URL_PREFIX
               (use during development so no AWS keys are needed)
  - "s3"     → uploads to Lightsail Object Storage / S3-compatible bucket

Always returns the public URL string that should be stored in house_images.url.
"""
import os
import uuid
from pathlib import Path
from typing import IO

from flask import current_app


def _ext(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()


def is_allowed(filename: str) -> bool:
    allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    return _ext(filename) in allowed


def upload_image(file_storage) -> str:
    """
    Accepts a Werkzeug FileStorage object. Returns the public URL.
    Caller is responsible for validating that file_storage is non-empty
    and is_allowed(file_storage.filename) is True.
    """
    ext = _ext(file_storage.filename) or "jpg"
    key = f"houses/{uuid.uuid4().hex}.{ext}"

    backend = current_app.config["STORAGE_BACKEND"]
    if backend == "s3":
        return _upload_s3(file_storage, key)
    return _upload_local(file_storage, key)


def _upload_local(file_storage, key: str) -> str:
    base_dir = Path(current_app.config["LOCAL_UPLOAD_DIR"])
    target = base_dir / key
    target.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(target)
    url_prefix = current_app.config["LOCAL_UPLOAD_URL_PREFIX"].rstrip("/")
    return f"{url_prefix}/{key}"


def _upload_s3(file_storage, key: str) -> str:
    import boto3

    cfg = current_app.config
    client = boto3.client(
        "s3",
        region_name=cfg["S3_REGION"],
        endpoint_url=cfg["S3_ENDPOINT_URL"] or None,
        aws_access_key_id=cfg["S3_ACCESS_KEY"],
        aws_secret_access_key=cfg["S3_SECRET_KEY"],
    )
    content_type = file_storage.mimetype or "image/jpeg"
    client.upload_fileobj(
        file_storage,
        cfg["S3_BUCKET"],
        key,
        ExtraArgs={"ContentType": content_type, "ACL": "public-read"},
    )
    base = cfg["S3_PUBLIC_URL_BASE"].rstrip("/")
    return f"{base}/{key}"


def delete_image(url: str):
    """Best-effort delete. Failures are swallowed (we don't want a missing file to break the UI)."""
    backend = current_app.config["STORAGE_BACKEND"]
    try:
        if backend == "s3":
            _delete_s3(url)
        else:
            _delete_local(url)
    except Exception as e:
        current_app.logger.warning(f"Failed to delete image {url}: {e}")


def _delete_local(url: str):
    prefix = current_app.config["LOCAL_UPLOAD_URL_PREFIX"].rstrip("/")
    if not url.startswith(prefix):
        return
    rel = url[len(prefix):].lstrip("/")
    target = Path(current_app.config["LOCAL_UPLOAD_DIR"]) / rel
    if target.exists():
        target.unlink()


def _delete_s3(url: str):
    import boto3
    cfg = current_app.config
    base = cfg["S3_PUBLIC_URL_BASE"].rstrip("/")
    if not url.startswith(base):
        return
    key = url[len(base):].lstrip("/")
    client = boto3.client(
        "s3",
        region_name=cfg["S3_REGION"],
        endpoint_url=cfg["S3_ENDPOINT_URL"] or None,
        aws_access_key_id=cfg["S3_ACCESS_KEY"],
        aws_secret_access_key=cfg["S3_SECRET_KEY"],
    )
    client.delete_object(Bucket=cfg["S3_BUCKET"], Key=key)
