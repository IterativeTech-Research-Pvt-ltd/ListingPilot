"""
Product photos in Supabase Storage. Only the backend writes them, with the service key from the environment;
the browser gets a signed link back. A photo is a JPEG or PNG (by its content, not its name) of at most 10 MB.
There is no fallback: when storage isn't configured or doesn't answer, the upload fails.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple

import httpx

from app.core.config import settings

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # the bucket's own limit
# Signed links Meesho fetches the photos through; a Supabase signed link with a long expiry was accepted (3 Nov 2026)
SIGNED_LINK_SECONDS = 5 * 365 * 24 * 3600
# Only a recent form upload can be discarded: this exact name, made by upload_product_photo, and still fresh.
# The route has no login, so seeded photos (SKU_1.jpg) and anything older stay out of reach by design.
_UPLOAD_NAME = re.compile(r"[A-Za-z0-9_-]{1,60}_([0-9]{14})(?:_ai)?_[0-9a-f]{6}\.(?:jpg|png)")
# A generated image's name has "_ai" after the time, where no SKU can put it (a SKU may end in "_ai")
_GENERATED_NAME = re.compile(r"_[0-9]{14}_ai_[0-9a-f]{6}\.(?:jpg|png)$")
DISCARD_WINDOW = timedelta(hours=24)
MAX_DISCARD = 10
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


class PhotoRejected(ValueError):
    """The file isn't a photo ListingPilot accepts; the message says what to do."""


class StorageUnavailable(RuntimeError):
    """Storage isn't configured or didn't accept the photo; nothing was saved."""


def photo_type(content: bytes) -> Tuple[str, str]:
    """(MIME type, extension) of a JPEG or PNG, read from the file's first bytes."""
    if not content:
        raise PhotoRejected("The file is empty.")
    if len(content) > MAX_IMAGE_BYTES:
        raise PhotoRejected(f"The photo is {len(content) / 1024 / 1024:.1f} MB; the limit is 10 MB.")
    for signature, mime, ext in _SIGNATURES:
        if content.startswith(signature):
            return mime, ext
    raise PhotoRejected("Only JPEG and PNG photos are accepted. Convert the photo and upload it again.")


def is_generated_photo(url: str) -> bool:
    """True for a link to an AI-generated image this app stored; real photos and other links are False."""
    return bool(_GENERATED_NAME.search(str(url).split("?", 1)[0]))


def discardable_photo_name(url: str) -> str:
    """The bucket object behind a signed link from a recent upload; PhotoRejected for anything else."""
    prefix = f"{(settings.SUPABASE_URL or '').rstrip('/')}/storage/v1/object/sign/{settings.SUPABASE_STORAGE_BUCKET}/"
    name = url[len(prefix):].split("?", 1)[0] if settings.SUPABASE_URL and url.startswith(prefix) else ""
    match = _UPLOAD_NAME.fullmatch(name)
    if not match:
        raise PhotoRejected("That isn't a photo uploaded in this form.")
    try:
        uploaded = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        raise PhotoRejected("That isn't a photo uploaded in this form.")
    age = datetime.now(timezone.utc) - uploaded
    if age > DISCARD_WINDOW or age < -timedelta(minutes=5):
        raise PhotoRejected("That photo is too old to discard here.")
    return name


def delete_photo(name: str) -> None:
    """Removes one object from the bucket; a photo already gone counts as removed."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY and settings.SUPABASE_STORAGE_BUCKET):
        raise StorageUnavailable("Photo storage isn't configured.")
    base = settings.SUPABASE_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}", "apikey": settings.SUPABASE_SERVICE_KEY}
    try:
        with httpx.Client(timeout=60) as client:
            res = client.delete(f"{base}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{name}", headers=headers)
    except httpx.RequestError as e:
        raise StorageUnavailable(f"Couldn't reach photo storage: {e.__class__.__name__}.")
    if res.status_code >= 300 and res.status_code != 404:
        raise StorageUnavailable(f"Storage refused to delete the photo (HTTP {res.status_code}).")
    print(f"[Storage] Removed {name}", flush=True)


def upload_product_photo(content: bytes, sku: str, generated: bool = False) -> str:
    """Stores the photo as '<SKU>_<time>_<id>.<ext>' ('<SKU>_<time>_ai_<id>.<ext>' when AI-generated) and returns a signed link to it."""
    mime, ext = photo_type(content)
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY and settings.SUPABASE_STORAGE_BUCKET):
        raise StorageUnavailable("Photo storage isn't configured (SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_STORAGE_BUCKET).")
    base = settings.SUPABASE_URL.rstrip("/")
    bucket = settings.SUPABASE_STORAGE_BUCKET
    safe_sku = re.sub(r"[^A-Za-z0-9_-]", "_", sku or "product")[:60]
    marker = "_ai" if generated else ""
    name = f"{safe_sku}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{marker}_{uuid.uuid4().hex[:6]}.{ext}"
    headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}", "apikey": settings.SUPABASE_SERVICE_KEY}
    try:
        with httpx.Client(timeout=60) as client:
            res = client.post(f"{base}/storage/v1/object/{bucket}/{name}", content=content,
                              headers={**headers, "Content-Type": mime})
            if res.status_code >= 300:
                raise StorageUnavailable(f"Storage refused the photo (HTTP {res.status_code}): {res.text[:200]}")
            signed = client.post(f"{base}/storage/v1/object/sign/{bucket}/{name}",
                                 json={"expiresIn": SIGNED_LINK_SECONDS}, headers=headers)
            if signed.status_code >= 300:
                raise StorageUnavailable(f"The photo was stored but no link could be made (HTTP {signed.status_code}).")
            path = signed.json().get("signedURL") or signed.json().get("signedUrl")
    except httpx.RequestError as e:
        raise StorageUnavailable(f"Couldn't reach photo storage: {e.__class__.__name__}.")
    if not path:
        raise StorageUnavailable("Storage returned no signed link for the photo.")
    print(f"[Storage] Stored {name} ({len(content) // 1024} KB)", flush=True)
    return f"{base}/storage/v1{path}"
