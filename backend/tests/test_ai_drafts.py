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


def test_regenerate_preview_does_not_touch_saved_draft_until_saved():
    """Regenerate with preview=true fills the editor only; Save (PUT) is what replaces the DB copy."""
    product_id = client.get("/api/v1/catalogue/products?category=Bedsheets").json()["items"][0]["id"]
    old_copy = {**MOCK_LISTING, "title": "Gulmohar Home Old Saved Title For Bedsheet Double Cotton 180 TC"}
    new_copy = {**MOCK_LISTING, "title": "Gulmohar Home Brand New AI Title For Bedsheet Double Cotton 180 TC"}

    # A saved draft exists with the old copy
    with patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock, return_value=old_copy):
        saved = client.post(f"/api/v1/drafts/generate/{product_id}?marketplace=flipkart").json()
    assert saved.get("preview") is not True

    # Regenerate as a preview: response carries the new copy, DB keeps the old one
    with patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock, return_value=new_copy):
        preview = client.post(f"/api/v1/drafts/generate/{product_id}?marketplace=flipkart&preview=true").json()
    assert preview["preview"] is True
    assert preview["id"] == saved["id"]
    assert preview["title"] == new_copy["title"]
    in_db = client.get(f"/api/v1/drafts/product/{product_id}?marketplace=flipkart").json()
    assert in_db["title"] == old_copy["title"]

    # Saving the editor content replaces the DB copy
    put = client.put(f"/api/v1/drafts/{saved['id']}", json={"title": preview["title"], "bullets": preview["bullets"]})
    assert put.status_code == 200
    in_db = client.get(f"/api/v1/drafts/product/{product_id}?marketplace=flipkart").json()
    assert in_db["title"] == new_copy["title"]


def test_preview_without_existing_draft_creates_it():
    import uuid
    product = client.post("/api/v1/catalogue/products", json={
        "sku": f"PREVIEW-{uuid.uuid4().hex[:8]}", "name": "Preview test bedsheet", "category": "Bedsheets",
        "price": 999, "stock": 5, "attributes": {"Material": "Cotton"},
    }).json()

    with patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock, return_value=MOCK_LISTING):
        res = client.post(f"/api/v1/drafts/generate/{product['id']}?marketplace=meesho&preview=true").json()

    assert res.get("preview") is not True
    assert client.get(f"/api/v1/drafts/product/{product['id']}?marketplace=meesho").json()["id"] == res["id"]
