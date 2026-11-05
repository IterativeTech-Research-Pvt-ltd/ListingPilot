"""Product photos go to Supabase Storage through the backend: JPEG/PNG only, 10 MB, no local fallback."""
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import storage_service

client = TestClient(app)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 2000


def upload(content, name="photo.jpg", sku="JBP-101"):
    return client.post("/api/v1/catalogue/upload-image", files={"file": (name, content, "application/octet-stream")},
                       data={"sku": sku})


@pytest.fixture
def storage(monkeypatch):
    """Configured storage whose HTTP calls are recorded; nothing reaches Supabase."""
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "service-key-for-tests")
    monkeypatch.setattr(settings, "SUPABASE_STORAGE_BUCKET", "product-images")
    http = MagicMock()
    http.post.side_effect = lambda url, **kw: (
        httpx.Response(200, json={"signedURL": "/object/sign/product-images/x.jpg?token=t"}) if "/object/sign/" in url
        else httpx.Response(200, json={"Key": "product-images/x.jpg"}))
    with patch.object(storage_service.httpx, "Client") as client_cls:
        client_cls.return_value.__enter__.return_value = http
        yield http


def test_a_jpeg_is_stored_by_the_backend_and_gets_a_signed_link(storage):
    res = upload(JPEG)
    assert res.status_code == 200, res.text
    url = res.json()["url"]
    assert url == "https://proj.supabase.co/storage/v1/object/sign/product-images/x.jpg?token=t"
    stored_url, kwargs = storage.post.call_args_list[0].args[0], storage.post.call_args_list[0].kwargs
    assert "/storage/v1/object/product-images/JBP-101_" in stored_url and stored_url.endswith(".jpg")
    assert kwargs["headers"]["Content-Type"] == "image/jpeg" and kwargs["content"] == JPEG
    assert storage.post.call_args_list[1].kwargs["json"]["expiresIn"] == storage_service.SIGNED_LINK_SECONDS
    assert "service-key-for-tests" not in res.text  # the key never reaches the browser


def test_a_png_keeps_its_type(storage):
    assert upload(PNG, name="photo.png").status_code == 200
    assert storage.post.call_args_list[0].kwargs["headers"]["Content-Type"] == "image/png"


@pytest.mark.parametrize("content, name, reason", [
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "photo.webp", "Only JPEG and PNG"),
    (b"GIF89a" + b"0" * 100, "photo.gif", "Only JPEG and PNG"),
    (b"<html>not a photo</html>", "photo.jpg", "Only JPEG and PNG"),  # the name doesn't make it a JPEG
    (b"", "photo.jpg", "empty"),
    (b"\xff\xd8\xff" + b"0" * storage_service.MAX_IMAGE_BYTES, "big.jpg", "the limit is 10 MB"),
], ids=["webp", "gif", "html-named-jpg", "empty", "over-10-mb"])
def test_anything_but_a_jpeg_or_png_up_to_10_mb_is_refused(storage, content, name, reason):
    res = upload(content, name=name)
    assert res.status_code == 422 and reason in res.json()["detail"]
    storage.post.assert_not_called()


def test_without_storage_configured_the_upload_fails_and_nothing_is_kept(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    res = upload(JPEG)
    assert res.status_code == 503 and "isn't configured" in res.json()["detail"]


def test_unreachable_storage_fails_the_upload(storage):
    storage.post.side_effect = httpx.ConnectError("no route")
    res = upload(JPEG)
    assert res.status_code == 503 and "Couldn't reach photo storage" in res.json()["detail"]


def test_storage_refusing_the_photo_fails_the_upload(storage):
    storage.post.side_effect = lambda url, **kw: httpx.Response(413, text="Payload too large")
    res = upload(JPEG)
    assert res.status_code == 503 and "HTTP 413" in res.json()["detail"]
