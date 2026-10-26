import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

MOCK_LISTING = {
    "title": "Gulmohar Home Hand block print double bedsheet with 2 pillow covers (90 x 100 in, 180 TC)",
    "bullets": [
        "PREMIUM 100% COTTON: Breathable pure cotton fabric for comfort.",
        "GENEROUS DIMENSIONS: 90 x 100 in double bedsheet with matching pillow covers.",
        "HAND BLOCK PRINT: Authentic artisan dyed heritage pattern.",
        "DURABLE THREAD COUNT: 180 TC woven structure for long life.",
        "CARE INSTRUCTIONS: Machine wash cold with similar colors."
    ],
    "description": "Premium handcrafted bedsheet set from Gulmohar Home.",
    "keywords": ["cotton bedsheet", "gulmohar home", "double bed"]
}

@patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock)
def test_generate_and_approve_draft(mock_gen):
    mock_gen.return_value = MOCK_LISTING

    # 1. Get first product
    prod_res = client.get("/api/v1/catalogue/products?page_size=1")
    assert prod_res.status_code == 200
    product = prod_res.json()["items"][0]
    p_id = product["id"]

    # 2. Generate AI Draft (GEN-1 - GEN-4)
    gen_res = client.post(f"/api/v1/drafts/generate/{p_id}?marketplace=amazon")
    assert gen_res.status_code == 200
    draft = gen_res.json()
    assert draft["product_id"] == p_id
    assert len(draft["title"]) > 10
    assert len(draft["bullets"]) == 5
    assert len(draft["keywords"]) >= 3
    assert "rule_results" in draft

    draft_id = draft["id"]

    # 3. Edit Draft (WF-2: human editing resets approval & re-checks)
    edit_res = client.put(f"/api/v1/drafts/{draft_id}", json={
        "title": "Gulmohar Home Updated Artisan Edition Double Bedsheet 90x100 in"
    })
    assert edit_res.status_code == 200
    updated_draft = edit_res.json()
    assert updated_draft["is_approved"] is False

    # 4. Human Approval (WF-2)
    # If there are no blocking errors, approve it
    if not updated_draft["rule_results"].get("has_errors"):
        appr_res = client.post(f"/api/v1/drafts/{draft_id}/approve")
        assert appr_res.status_code == 200
        assert appr_res.json()["is_approved"] is True
        assert appr_res.json()["status"] == "approved"

@patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock)
def test_banned_claim_detection(mock_gen):
    mock_gen.return_value = MOCK_LISTING

    # Verify that promotional claims are caught by RuleEngine (RUL-4)
    prod_res = client.get("/api/v1/catalogue/products?page_size=1")
    product = prod_res.json()["items"][0]
    p_id = product["id"]

    gen_res = client.post(f"/api/v1/drafts/generate/{p_id}?marketplace=amazon")
    draft_id = gen_res.json()["id"]

    # Injected banned claim "Free delivery"
    bad_edit = client.put(f"/api/v1/drafts/{draft_id}", json={
        "title": "Gulmohar Home Jaipuri Bedsheet with Free Delivery Guaranteed"
    })
    assert bad_edit.status_code == 200
    issues = bad_edit.json()["rule_results"]["issues"]
    assert bad_edit.json()["status"] == "draft"
    assert bad_edit.json()["rule_results"]["has_errors"] is True

    # Approval should be rejected when errors are present
    appr_fail = client.post(f"/api/v1/drafts/{draft_id}/approve")
    assert appr_fail.status_code == 400
