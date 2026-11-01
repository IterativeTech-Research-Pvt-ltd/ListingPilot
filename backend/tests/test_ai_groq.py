import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import settings
from app.models.product import Product
from app.services import ai_service
from app.services.ai_service import AIService, GROQ_CHAT_URL
from app.services.settings_service import SettingsService

LISTING_JSON = json.dumps({
    "title": "Gulmohar Home Cotton Double Bedsheet Indigo Floral Hand Block Print",
    "bullets": ["STYLE — a", "MATERIAL — b", "SIZE — c", "CONTENTS — d", "CARE — e"],
    "description": "Hand block printed cotton bedsheet.",
    "keywords": ["cotton bedsheet", "double bedsheet"],
})


def _product():
    return Product(
        id=1, sku="JBP-101", name="Hand block print double bedsheet", category="Bedsheets",
        brand="Gulmohar Home", price=1299, attributes={"Material": "100% cotton"}, images=[],
    )


def _response(status, url, json_body=None, headers=None):
    return httpx.Response(status, request=httpx.Request("POST", url), json=json_body or {}, headers=headers)


def _ok(url):
    return _response(200, url, {"choices": [{"message": {"content": LISTING_JSON}}]})


@pytest.fixture(autouse=True)
def groq_settings(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")
    ai_service._MODEL_COOLDOWN_UNTIL.clear()
    yield
    ai_service._MODEL_COOLDOWN_UNTIL.clear()


def test_groq_provider_calls_groq_with_json_mode():
    calls = []

    async def fake_post(self, url, headers=None, json=None):
        calls.append((url, headers, json))
        return _ok(url)

    with patch.object(httpx.AsyncClient, "post", fake_post):
        result = asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert result["title"].startswith("Gulmohar Home Cotton")
    assert "engine" not in result  # came from the model, not the built-in generator
    url, headers, payload = calls[0]
    assert url == GROQ_CHAT_URL
    assert headers["Authorization"] == "Bearer gsk_test_key"
    assert payload["model"] == "openai/gpt-oss-120b"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["reasoning_effort"] == "low"
    assert "openrouter.ai" not in url


def test_model_output_missing_fields_is_normalized_not_a_crash():
    # Bullets sent as one string, keywords missing, specs as a list: the draft code reads all of these
    reply = json.dumps({"title": "Gulmohar Home Cotton Bedsheet", "bullets": "STYLE — a\nMATERIAL — b",
                        "description": "Cotton bedsheet.", "technical_specs": ["not", "a", "dict"]})

    async def fake_post(self, url, headers=None, json=None):
        return _response(200, url, {"choices": [{"message": {"content": reply}}]})

    with patch.object(httpx.AsyncClient, "post", fake_post):
        result = asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert "engine" not in result
    assert result["bullets"] == ["STYLE — a", "MATERIAL — b"]
    assert result["keywords"] == []
    assert result["technical_specs"] == {"Material": "100% cotton"}  # only the product's own attribute


def test_description_written_into_the_bullets_tries_the_next_model():
    # Seen from gpt-oss: the description ends up as extra strings in the bullet list
    broken = json.dumps({"title": "Gulmohar Home Cotton Bedsheet",
                         "bullets": ["A", "B", "C", "D", "E", "description", ":", *["Elevate your bedroom"] * 6]})
    calls = []

    async def fake_post(self, url, headers=None, json=None):
        calls.append(json["model"])
        return _ok(url) if len(calls) > 1 else _response(200, url, {"choices": [{"message": {"content": broken}}]})

    with patch.object(httpx.AsyncClient, "post", fake_post):
        result = asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert len(calls) == 2  # first model's reply rejected, second model's used
    assert result["description"] == "Hand block printed cotton bedsheet."
    assert len(result["bullets"]) == 5


def test_reasoning_effort_sent_only_to_gpt_oss_models(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b")
    payloads = []

    async def fake_post(self, url, headers=None, json=None):
        payloads.append(json)
        return _ok(url)

    with patch.object(httpx.AsyncClient, "post", fake_post):
        asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert payloads[0]["model"] == "qwen/qwen3.8-27b"
    assert "reasoning_effort" not in payloads[0]


def test_short_rate_limit_is_waited_out_and_retried():
    attempts = []

    async def fake_post(self, url, headers=None, json=None):
        attempts.append(json["model"])
        if len(attempts) == 1:
            return _response(429, url, headers={"retry-after": "2"})
        return _ok(url)

    with patch.object(httpx.AsyncClient, "post", fake_post), \
         patch("app.services.ai_service.asyncio.sleep", new_callable=AsyncMock) as sleep:
        result = asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert attempts == ["openai/gpt-oss-120b", "openai/gpt-oss-120b"]
    sleep.assert_awaited_once_with(2.0)
    assert "engine" not in result


def test_long_rate_limit_cools_down_model_and_uses_next_groq_model():
    attempts = []

    async def fake_post(self, url, headers=None, json=None):
        attempts.append(json["model"])
        if json["model"] == "openai/gpt-oss-120b":
            return _response(429, url, headers={"retry-after": "120"})
        return _ok(url)

    with patch.object(httpx.AsyncClient, "post", fake_post):
        asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))
        attempts.clear()
        asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    # The rate-limited model is skipped on the next request
    assert attempts == ["qwen/qwen3.8-27b"]


def test_missing_groq_key_uses_builtin_generator(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)

    async def fail_post(self, url, headers=None, json=None):
        raise AssertionError("no HTTP call expected without a key")

    with patch.object(httpx.AsyncClient, "post", fail_post):
        result = asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert result["engine"] == "category_agnostic_rule_engine"


def test_settings_report_groq_as_ai_engine():
    engine = SettingsService.get_masked_credentials()["ai_engine"]
    assert engine["provider"] == "groq"
    assert engine["model"] == "openai/gpt-oss-120b"
    assert engine["has_api_key"] is True
    assert "gsk_test_key" not in engine["api_key_masked"]


def test_waits_for_cooled_down_model_instead_of_template_copy():
    """All models rate-limited for 30s: wait for the first to free up, then use AI, not template copy."""
    attempts = []

    async def fake_post(self, url, headers=None, json=None):
        attempts.append(json["model"])
        if len(attempts) <= 3:  # first pass: every Groq model is over its per-minute limit
            return _response(429, url, headers={"retry-after": "30"})
        return _ok(url)

    async def fake_sleep(seconds):
        # Simulate the cooldown elapsing
        for m in list(ai_service._MODEL_COOLDOWN_UNTIL):
            ai_service._MODEL_COOLDOWN_UNTIL[m] = 0

    with patch.object(httpx.AsyncClient, "post", fake_post), \
         patch("app.services.ai_service.asyncio.sleep", side_effect=fake_sleep) as sleep:
        result = asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert AIService.generation_source(result) == "ai"
    waited = sleep.call_args_list[-1].args[0]
    assert 0 < waited <= 30
    assert attempts[3] == "openai/gpt-oss-120b"  # retried the primary model after the wait


def test_long_cooldown_falls_back_to_template_without_waiting():
    async def fake_post(self, url, headers=None, json=None):
        return _response(429, url, headers={"retry-after": "300"})

    with patch.object(httpx.AsyncClient, "post", fake_post), \
         patch("app.services.ai_service.asyncio.sleep", new_callable=AsyncMock) as sleep:
        result = asyncio.run(AIService.generate_listing(_product(), marketplace="amazon"))

    assert AIService.generation_source(result) == "template"
    sleep.assert_not_awaited()


def test_batch_reports_ai_vs_template_counts():
    from fastapi.testclient import TestClient
    from app.main import app

    ai_copy = json.loads(LISTING_JSON)
    template_copy = {**ai_copy, "engine": ai_service.TEMPLATE_ENGINE}
    calls = {"n": 0}

    async def fake_generate(product, marketplace="amazon"):
        calls["n"] += 1
        return dict(template_copy if calls["n"] % 2 == 0 else ai_copy)

    with patch("app.services.ai_service.AIService.generate_listing", side_effect=fake_generate):
        res = TestClient(app).post("/api/v1/drafts/generate-batch?marketplace=meesho&category=Bedsheets&overwrite=true")

    data = res.json()
    assert res.status_code == 200
    assert data["generated"] == data["ai_generated"] + data["template_generated"]
    assert data["template_generated"] == calls["n"] // 2
    assert len(data["template_items"]) == data["template_generated"]
    assert all(t["marketplace"] == "meesho" for t in data["template_items"])


def test_single_generate_reports_generation_source():
    from fastapi.testclient import TestClient
    from app.main import app

    template_copy = {**json.loads(LISTING_JSON), "engine": ai_service.TEMPLATE_ENGINE}
    client = TestClient(app)
    product_id = client.get("/api/v1/catalogue/products?category=Bedsheets").json()["items"][0]["id"]

    with patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock, return_value=template_copy):
        res = client.post(f"/api/v1/drafts/generate/{product_id}?marketplace=meesho")

    assert res.status_code == 200
    assert res.json()["generation_source"] == "template"
