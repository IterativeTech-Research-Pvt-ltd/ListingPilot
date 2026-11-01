import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.settings_service import SettingsService
from app.services.rule_engine import RuleEngine
from app.models.product import Product

client = TestClient(app)

def test_get_settings():
    """Verify settings endpoint returns dynamic config with masked credentials (ADM-1, ADM-3)."""
    res = client.get("/api/v1/settings")
    assert res.status_code == 200
    data = res.json()
    assert "brand_voice" in data
    assert "banned_claims" in data
    assert "marketplace_limits" in data
    assert "credentials" in data
    
    # Check credentials masking (ADM-3)
    creds = data["credentials"]
    assert "amazon" in creds
    assert "flipkart" in creds
    assert "ai_engine" in creds
    assert "amazon_sp_api_client_secret" not in str(creds)  # Raw secret must never be exposed


def test_update_brand_voice():
    """Verify self-serve brand voice updating (ADM-1)."""
    payload = {
        "brand_name": "Royal Rajputana Craft",
        "tone": "Regal, heritage, artisanal luxury craftsmanship",
        "target_audience": "Global connoisseurs of handcrafted Indian textiles",
        "avoid_claims": "Never use modern synthetic claims or mass manufactured terms"
    }
    res = client.put("/api/v1/settings/brand-voice", json=payload)
    assert res.status_code == 200
    updated = res.json()
    assert updated["brand_name"] == "Royal Rajputana Craft"
    assert updated["tone"] == "Regal, heritage, artisanal luxury craftsmanship"

    # Verify retrieval
    get_res = client.get("/api/v1/settings")
    assert get_res.json()["brand_voice"]["brand_name"] == "Royal Rajputana Craft"


def test_dynamic_banned_claims_and_rule_engine_integration():
    """Verify dynamic banned claims updating immediately enforces compliance in RuleEngine (ADM-1, RUL-4)."""
    # 1. Fetch existing claims
    get_res = client.get("/api/v1/settings/banned-claims")
    assert get_res.status_code == 200
    current_claims = get_res.json()
    assert "free delivery" in current_claims

    # 2. Add a new banned claim: "unbeatable price"
    new_claims = current_claims + ["unbeatable price"]
    put_res = client.put("/api/v1/settings/banned-claims", json={"banned_claims": new_claims})
    assert put_res.status_code == 200
    assert "unbeatable price" in put_res.json()

    # 3. Test that RuleEngine immediately catches the new claim
    dummy_prod = Product(
        sku="TEST-ADM-SKU",
        name="Artisan Bedcover",
        category="Bedsheets",
        brand="Royal Rajputana Craft",
        price=1899.0,
        images=["https://images.example.com/bed1.jpg", "https://images.example.com/bed2.jpg", "https://images.example.com/bed3.jpg"],
        attributes={"Material": "100% Cotton", "Size": "King Size"}
    )
    draft_with_new_claim = {
        "title": "Royal Rajputana Craft Artisan Bedcover King Size at Unbeatable Price",
        "bullets": ["AUTHENTIC: Handcrafted bedcover", "COTTON: 100% Cotton", "DIMENSIONS: King size", "INCLUSIONS: 1 bedcover", "CARE: Gentle wash"],
        "description": "Premium bedcover crafted with love.",
        "keywords": ["bedcover", "cotton"]
    }

    eval_result = RuleEngine.evaluate(dummy_prod, draft=draft_with_new_claim, marketplace="amazon")
    assert eval_result["has_errors"] is True
    assert any("unbeatable price" in i["message"].lower() for i in eval_result["issues"])
    assert any(i["kind"] == "banned_claim" for i in eval_result["issues"])


def test_update_credentials_masked(monkeypatch):
    """Verify credentials updating and masking (ADM-3)."""
    # The AI engine status follows AI_PROVIDER; pin it so a saved OpenRouter key is what's reported
    from app.core.config import settings
    monkeypatch.setattr(settings, "AI_PROVIDER", "openrouter")
    update_payload = {
        "amazon_seller_id": "TEST_SELLER_ID",
        "amazon_sp_api_client_id": "test-client-id-1234567890",
        "flipkart_app_id": "test-flipkart-app-id",
        "openrouter_api_key": "sk-or-v1-abcdef-test-only"
    }
    put_res = client.put("/api/v1/settings/credentials", json=update_payload)
    assert put_res.status_code == 200
    creds = put_res.json()
    
    assert creds["amazon"]["seller_id"] == "TEST_SELLER_ID"
    assert creds["amazon"]["has_client_id"] is True
    assert "1234567890" not in creds["amazon"]["client_id_masked"]  # masked
    assert creds["flipkart"]["has_app_id"] is True
    assert creds["ai_engine"]["has_api_key"] is True


def test_system_health_monitoring():
    """Verify system health, sync status, and alert generation (ADM-4)."""
    res = client.get("/api/v1/settings/system-health")
    assert res.status_code == 200
    health = res.json()
    assert health["status"] == "healthy"
    assert health["phase"] == 4
    assert "services" in health
    assert "database" in health["services"]
    assert "ai_content_engine" in health["services"]
    assert "amazon_sp_api" in health["services"]
    assert "flipkart_seller_api" in health["services"]
    assert "meesho_exporter" in health["services"]
    assert "last_sync" in health
    assert "active_alerts" in health


def test_system_health_reports_an_unreachable_database():
    """The database status comes from a real query, never a hard-coded 'connected'."""
    from sqlalchemy.exc import OperationalError
    from app.services.settings_service import SettingsService

    assert client.get("/api/v1/settings/system-health").json()["services"]["database"]["status"] == "connected"

    class DeadSession:
        def execute(self, *_a, **_k):
            raise OperationalError("SELECT 1", {}, Exception('could not translate host name "db.x.supabase.co"\n'))

    health = SettingsService.get_system_health(DeadSession())
    assert health["status"] == "degraded"
    assert health["services"]["database"]["status"] == "unreachable"
    assert "could not translate host name" in health["services"]["database"]["error"]
    assert any(a["channel"] == "database" for a in health["active_alerts"])
