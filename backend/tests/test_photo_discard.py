"""A photo uploaded in Add Product is removed again when the product isn't added, and nothing else can be removed."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import storage_service

client = TestClient(app)
BASE = "https://proj.supabase.co"


def name_uploaded(ago=timedelta(minutes=1), sku="NEW-1", ext="jpg"):
    stamp = (datetime.now(timezone.utc) - ago).strftime("%Y%m%d%H%M%S")
    return f"{sku}_{stamp}_{uuid.uuid4().hex[:6]}.{ext}"


def link(name, base=BASE, bucket="product-images"):
    return f"{base}/storage/v1/object/sign/{bucket}/{name}?token=t"


def discard(*urls):
    return client.post("/api/v1/catalogue/discard-images", data={"urls": list(urls)})


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", BASE)
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "service-key-for-tests")
    monkeypatch.setattr(settings, "SUPABASE_STORAGE_BUCKET", "product-images")
    http = MagicMock()
    http.delete.return_value = httpx.Response(200, json={"message": "Successfully deleted"})
    with patch.object(storage_service.httpx, "Client") as client_cls:
        client_cls.return_value.__enter__.return_value = http
        yield http


def test_an_unused_new_upload_is_removed_from_the_bucket(storage):
    first, second = name_uploaded(), name_uploaded(ext="png")
    res = discard(link(first), link(second))
    assert res.status_code == 200, res.text
    assert res.json() == {"removed": 2, "kept": 0}
    deleted = [c.args[0] for c in storage.delete.call_args_list]
    assert deleted == [f"{BASE}/storage/v1/object/product-images/{first}", f"{BASE}/storage/v1/object/product-images/{second}"]
    assert storage.delete.call_args.kwargs["headers"]["apikey"] == "service-key-for-tests"


def test_a_photo_already_gone_counts_as_removed(storage):
    storage.delete.return_value = httpx.Response(404, json={"message": "not found"})
    assert discard(link(name_uploaded())).json() == {"removed": 1, "kept": 0}


def test_a_photo_a_product_uses_is_kept(storage):
    used = name_uploaded()
    res = client.post("/api/v1/catalogue/products", json={
        "sku": f"KEEP-{uuid.uuid4().hex[:8]}", "name": "Uses the photo", "category": "Bedsheets", "price": 999, "stock": 1,
        "images": [link(used)],
    })
    assert res.status_code == 201, res.text

    res = discard(link(used))
    assert res.status_code == 200
    assert res.json() == {"removed": 0, "kept": 1}
    storage.delete.assert_not_called()


@pytest.mark.parametrize("url", [
    link("JBP-101_1.jpg"),                                     # a seeded photo, not a form upload
    link(name_uploaded(ago=timedelta(hours=25))),              # too old to be this form's upload
    link(name_uploaded(), base="https://evil.example.com"),    # someone else's storage
    link(name_uploaded(), bucket="other-bucket"),              # another bucket
    link(f"../other-bucket/{name_uploaded()}"),                # path traversal
    link(f"folder/{name_uploaded()}"),
    "https://images.example.com/photo.jpg",
    "not a link",
], ids=["seed-photo", "old-upload", "other-host", "other-bucket", "traversal", "subfolder", "web-link", "garbage"])
def test_anything_else_is_refused_and_nothing_is_removed(storage, url):
    res = discard(link(name_uploaded()), url)
    assert res.status_code == 422, res.text
    assert "Nothing was removed" in res.json()["detail"]
    storage.delete.assert_not_called()


def test_too_many_at_once_is_refused(storage):
    res = discard(*[link(name_uploaded()) for _ in range(storage_service.MAX_DISCARD + 1)])
    assert res.status_code == 422
    storage.delete.assert_not_called()


def test_storage_refusing_fails_loudly(storage):
    storage.delete.return_value = httpx.Response(500, text="boom")
    res = discard(link(name_uploaded()))
    assert res.status_code == 503
    assert "not removed" in res.json()["detail"].lower()


def test_storage_unreachable_fails_loudly(storage):
    storage.delete.side_effect = httpx.ConnectError("down")
    assert discard(link(name_uploaded())).status_code == 503


def test_no_storage_address_means_no_link_can_be_ours(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    assert discard(link(name_uploaded())).status_code == 422


def test_storage_without_its_key_fails_loudly(storage, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    assert discard(link(name_uploaded())).status_code == 503
    storage.delete.assert_not_called()


@pytest.mark.parametrize("name", [
    "NEW-1_99999999999999_abc123.jpg",   # no such date
    "NEW-1_20261399000000_abc123.jpg",   # month 13
    "NEW-1_20991231235959_abc123.jpg",   # the future
    "NEW-1_٢٠٢٦١١٠٥١٢٠٠٠٠_abc123.jpg",   # digits of another script
    "NEW-1_20261105120000_abc123.JPG",
    "NEW-1%5F20261105120000_abc123.jpg",
], ids=["no-such-date", "month-13", "future", "non-ascii-digits", "upper-case-ext", "percent-encoded"])
def test_a_name_upload_never_makes_is_refused(storage, name):
    res = discard(link(name))
    assert res.status_code == 422, res.text
    storage.delete.assert_not_called()


def test_used_and_unused_photos_in_one_request(storage):
    used, unused = name_uploaded(), name_uploaded()
    assert client.post("/api/v1/catalogue/products", json={
        "sku": f"KEEP-{uuid.uuid4().hex[:8]}", "name": "Uses one photo", "category": "Bedsheets", "price": 999, "stock": 1,
        "images": [f"{BASE}/storage/v1/object/public/product-images/{used}"],  # any link form of the same file
    }).status_code == 201

    assert discard(link(used), link(unused)).json() == {"removed": 1, "kept": 1}
    assert [c.args[0].rsplit("/", 1)[1] for c in storage.delete.call_args_list] == [unused]


def test_no_links_is_refused(storage):
    assert client.post("/api/v1/catalogue/discard-images", data={}).status_code == 422


def test_the_answer_carries_no_token_or_key(storage):
    body = discard(link(name_uploaded())).text
    assert "token" not in body and "service-key" not in body
