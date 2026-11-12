"""Generated product images: Cloudflare Workers AI through ai_service.py, stored like any upload. Nothing here reaches a real service."""
import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.api.v1.endpoints import catalogue
from app.main import app
from app.services import ai_service, storage_service
from app.services.ai_service import AIService

client = TestClient(app)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000
FORM = {"sku": "NEW-1", "name": "Blue pottery planter", "category": "Planters", "details": "Material: ceramic; Color: Blue"}


def generate(content=JPEG, **fields):
    return client.post("/api/v1/catalogue/generate-image", files={"file": ("photo.jpg", content, "image/jpeg")},
                       data={**FORM, **fields})


def cloudflare_ok(image=JPEG):
    return httpx.Response(200, json={"result": {"image": base64.b64encode(image).decode()}, "success": True})


@pytest.fixture
def services(monkeypatch):
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setattr(settings, "CLOUDFLARE_AI_TOKEN", "cf-token-for-tests")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "service-key-for-tests")
    monkeypatch.setattr(settings, "SUPABASE_STORAGE_BUCKET", "product-images")
    http = MagicMock()
    http.cloudflare = cloudflare_ok()

    def post(url, **kwargs):
        if "api.cloudflare.com" in url:
            if isinstance(http.cloudflare, Exception):
                raise http.cloudflare
            return http.cloudflare
        if "/object/sign/" in url:
            return httpx.Response(200, json={"signedURL": "/object/sign/product-images/x.jpg?token=t"})
        return httpx.Response(200, json={"Key": "x"})

    http.post.side_effect = post
    with patch.object(ai_service.httpx, "Client") as client_cls:
        client_cls.return_value.__enter__.return_value = http
        yield http


def calls(http, text):
    return [c for c in http.post.call_args_list if text in c.args[0]]


def test_the_image_is_made_from_the_photo_and_stored(services):
    res = generate()
    assert res.status_code == 200, res.text
    assert res.json()["url"].startswith("https://proj.supabase.co/storage/v1/object/sign/")

    call = calls(services, "api.cloudflare.com")[0]
    assert call.args[0].endswith(f"/accounts/acct/ai/run/{settings.CLOUDFLARE_IMAGE_MODEL}")
    assert call.kwargs["headers"]["Authorization"] == "Bearer cf-token-for-tests"
    assert call.kwargs["files"]["input_image_0"][1] == JPEG
    assert call.kwargs["data"]["width"] == "1024" and call.kwargs["data"]["height"] == "1024"

    stored = [c.args[0] for c in calls(services, "/storage/v1/object/product-images/")][0]
    assert "/NEW-1_" in stored and "_ai_" in stored  # the name says it's generated
    assert storage_service.is_generated_photo(stored)  # the name the Meesho export uses to keep it out of Image 1
    assert "cf-token-for-tests" not in res.text and "service-key" not in res.text


def test_the_prompt_comes_from_the_form_and_guards_the_product():
    prompt = AIService.image_prompt("Blue pottery planter", "Planters", "Material: ceramic", "", 0)
    assert "Blue pottery planter" in prompt and "Planters" in prompt and "Material: ceramic" in prompt
    for rule in ("exactly", "No text", "no logos", "no people"):
        assert rule in prompt


def test_each_slot_gets_its_own_scene_and_the_sellers_note_is_used():
    prompts = {AIService.image_prompt("Planter", "Planters", "", "", slot) for slot in range(3)}
    assert len(prompts) == 3
    assert "on a balcony" in AIService.image_prompt("Planter", "Planters", "", "on a balcony", 0)
    assert AIService.image_prompt("Planter", "Planters", "", "", 7)  # any slot number is safe


def test_long_form_text_is_cut_before_it_reaches_the_prompt():
    prompt = AIService.image_prompt("Planter", "Planters", "Q" * 5000, "Z" * 5000, 0)
    assert prompt.count("Q") == 600 and prompt.count("Z") == 200


def test_a_generated_image_can_be_discarded_like_an_upload(services):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    name = f"NEW-1_{stamp}_ai_abc123.jpg"
    url = f"https://proj.supabase.co/storage/v1/object/sign/product-images/{name}?token=t"
    assert storage_service.discardable_photo_name(url) == name


def test_no_product_name_is_refused_before_any_call(services):
    res = generate(name="  ")
    assert res.status_code == 422
    assert "name" in res.json()["detail"].lower()
    services.post.assert_not_called()


@pytest.mark.parametrize("content", [b"<html>not a photo</html>", b""], ids=["not-an-image", "empty"])
def test_a_bad_source_file_is_refused_before_any_call(services, content):
    assert generate(content=content).status_code == 422
    services.post.assert_not_called()


def test_not_configured_fails_loudly(services, monkeypatch):
    monkeypatch.setattr(settings, "CLOUDFLARE_AI_TOKEN", "")
    res = generate()
    assert res.status_code == 503
    assert "CLOUDFLARE_AI_TOKEN" in res.json()["detail"]
    services.post.assert_not_called()


def test_the_daily_limit_says_so_and_stores_nothing(services):
    services.cloudflare = httpx.Response(429, json={"errors": [{"message": "limit"}]})
    res = generate()
    assert res.status_code == 503
    # Cloudflare sometimes sends this while quota remains, so the message reports what Cloudflare said
    assert res.json()["detail"].startswith("Cloudflare says today's free image limit is used up")
    assert not calls(services, "/storage/v1/")


@pytest.mark.parametrize("answer", [
    httpx.Response(500, text="boom"),
    httpx.Response(200, json={"result": {}}),
    httpx.Response(200, json={"result": {"image": "!!! not base64 !!!"}}),
    httpx.Response(200, text="not json"),
], ids=["server-error", "no-image", "bad-base64", "not-json"])
def test_a_bad_answer_fails_and_stores_nothing(services, answer):
    services.cloudflare = answer
    res = generate()
    assert res.status_code == 502, res.text
    assert not calls(services, "/storage/v1/")


def test_an_answer_that_isnt_a_photo_fails_and_stores_nothing(services):
    services.cloudflare = cloudflare_ok(b"<html>nope</html>")
    assert generate().status_code == 502
    assert not calls(services, "/storage/v1/")


def test_cloudflare_unreachable_fails_loudly(services):
    services.cloudflare = httpx.ConnectError("down")
    assert generate().status_code == 503


def test_storage_refusing_fails_loudly(services):
    def post(url, **kwargs):
        return cloudflare_ok() if "api.cloudflare.com" in url else httpx.Response(500, text="boom")
    services.post.side_effect = post
    res = generate()
    assert res.status_code == 503
    assert "not saved" in res.json()["detail"].lower()


def test_a_photo_too_big_for_this_route_is_refused(services):
    res = generate(content=b"\xff\xd8\xff" + b"0" * catalogue.MAX_GENERATION_PHOTO_BYTES)
    assert res.status_code == 422
    assert "1 MB" in res.json()["detail"]
    services.post.assert_not_called()


def test_long_names_are_cut_before_they_reach_the_prompt():
    prompt = AIService.image_prompt("Q" * 5000, "Z" * 5000, "", "", 0)
    assert prompt.count("Q") == 200 and prompt.count("Z") == 200


def test_only_two_images_are_made_at_once(services):
    held = [catalogue._image_slots.acquire(blocking=False) for _ in range(2)]
    try:
        assert all(held)
        res = generate()
        assert res.status_code == 429
        assert "already" in res.json()["detail"]
        services.post.assert_not_called()
    finally:
        for _ in held:
            catalogue._image_slots.release()


def test_a_failure_frees_its_place(services):
    services.cloudflare = httpx.Response(500, text="boom")
    for _ in range(3):
        assert generate().status_code == 502
    services.cloudflare = cloudflare_ok()
    assert generate().status_code == 200


@pytest.mark.parametrize("sku", ["S" * 80, "../../other-bucket/x", "a/b.c"], ids=["long", "traversal", "slash-dot"])
def test_the_stored_name_stays_safe_and_keeps_its_marker(services, sku):
    assert generate(sku=sku).status_code == 200
    stored = calls(services, "/storage/v1/object/product-images/")[0].args[0].rsplit("/product-images/", 1)[1]
    assert storage_service.is_generated_photo(stored)
    assert storage_service._UPLOAD_NAME.fullmatch(stored)


def test_a_real_upload_is_never_marked_generated_whatever_its_sku(services):
    res = client.post("/api/v1/catalogue/upload-image", files={"file": ("photo.jpg", JPEG, "image/jpeg")},
                      data={"sku": "planter_ai"})
    assert res.status_code == 200, res.text
    stored = calls(services, "/storage/v1/object/product-images/")[0].args[0]
    assert "/planter_ai_" in stored and not storage_service.is_generated_photo(stored)


def test_a_refused_token_leaks_nothing(services, capsys):
    services.cloudflare = httpx.Response(401, text="bad\nFORGED LOG LINE")
    res = generate()
    assert res.status_code == 502
    printed = capsys.readouterr().out
    assert "cf-token-for-tests" not in res.text + printed
    assert "\nFORGED" not in printed
