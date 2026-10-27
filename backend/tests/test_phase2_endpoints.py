import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.amazon_adapter import AmazonAdapter

client = TestClient(app)

def test_amazon_adapter_validation():
    status = AmazonAdapter.validate_credentials()
    assert "configured" in status
    assert "mode" in status
    assert status["mode"] in ("stub", "live")
    assert status["marketplace_id"] == "A21TJRUUN4KGV"

def test_marketplace_status_matrix():
    res = client.get("/api/v1/drafts/marketplace-status")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data
    if data["items"]:
        first = data["items"][0]
        assert "sku" in first
        assert "marketplaces" in first
        assert "amazon" in first["marketplaces"]
        assert "flipkart" in first["marketplaces"]
        assert "meesho" in first["marketplaces"]

def test_reports_baseline_metrics():
    res = client.get("/api/v1/reports/baseline")
    assert res.status_code == 200
    data = res.json()
    assert "overview" in data
    assert "pipeline" in data
    assert "quality" in data
    assert "marketplace" in data
    assert "total_products" in data["overview"]
    assert "avg_score" in data["quality"]

def test_draft_stats_endpoints():
    res1 = client.get("/api/v1/reports/draft-stats")
    assert res1.status_code == 200
    assert "total_drafts" in res1.json()

    res2 = client.get("/api/v1/drafts/stats")
    assert res2.status_code == 200
    assert "total_drafts" in res2.json()

@patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock)
@patch("app.services.amazon_adapter.AmazonAdapter.create_listing", new_callable=AsyncMock)
def test_reject_and_publish_flow(mock_create_listing, mock_generate_listing):
    # Setup mock return values for deterministic, offline testing
    mock_generate_listing.return_value = {
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

    mock_create_listing.return_value = {
        "success": True,
        "marketplace": "amazon",
        "sku": "JBP-101",
        "external_listing_id": "B09X123456",
        "status": "live",
        "submission_id": "sub-123456",
        "mode": "stub"
    }

    # 1. Fetch a product
    prod_res = client.get("/api/v1/catalogue/products?page_size=1")
    assert prod_res.status_code == 200
    items = prod_res.json().get("items", [])
    if not items:
        pytest.skip("No products in database to test publish flow")
    
    product_id = items[0]["id"]

    # 2. Generate Draft
    gen_res = client.post(f"/api/v1/drafts/generate/{product_id}?marketplace=amazon")
    assert gen_res.status_code == 200
    draft = gen_res.json()
    draft_id = draft["id"]

    # 3. Test Rejection flow
    rej_res = client.post(f"/api/v1/drafts/{draft_id}/reject", json={"reason": "Title needs revision"})
    assert rej_res.status_code == 200
    rej_data = rej_res.json()
    assert rej_data["status"] == "draft"
    assert rej_data["rejection_reason"] == "Title needs revision"
    assert rej_data["is_approved"] is False

    # 4. Attempt to publish rejected/unapproved draft (Must fail per WF-2)
    unapproved_pub = client.post(f"/api/v1/drafts/{draft_id}/publish")
    assert unapproved_pub.status_code == 400

    # 5. Fix & Approve draft
    clean_edit = client.put(f"/api/v1/drafts/{draft_id}", json={
        "title": "Gulmohar Home Handcrafted Artisanal Cotton Double Bedsheet 90x100 in",
        "bullets": [
          "PREMIUM 100% PURE COTTON: Breathable long-staple cotton yarns.",
          "DIMENSIONS: Standard 90 x 100 inch bedsheet with 2 pillow covers.",
          "HAND BLOCK PRINT: Crafted using heritage artisan dying techniques.",
          "DURABLE 180 THREAD COUNT: Machine washable and tear-resistant.",
          "CARE GUIDE: Wash in cold water on gentle cycle."
        ]
    })
    assert clean_edit.status_code == 200
    assert clean_edit.json()["rule_results"]["has_errors"] is False

    appr_res = client.post(f"/api/v1/drafts/{draft_id}/approve")
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # 6. Publish to Amazon (AMZ-1)
    pub_res = client.post(f"/api/v1/drafts/{draft_id}/publish")
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["draft"]["status"] == "live"
    assert pub_data["draft"]["external_listing_id"].startswith("B09")
    assert pub_data["publish_result"]["success"] is True

@patch("app.services.ai_service.AIService.generate_listing", new_callable=AsyncMock)
def test_batch_generation_endpoint(mock_generate):
    mock_generate.return_value = {
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

    res = client.post("/api/v1/drafts/generate-batch?marketplace=amazon&overwrite=true")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["generated"] >= 1

    # Test batch generation across ALL marketplaces (Amazon + Flipkart + Meesho)
    res_all = client.post("/api/v1/drafts/generate-batch?marketplace=all&overwrite=true")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["success"] is True
    assert data_all["marketplace"] == "all"
    assert data_all["marketplaces"] == ["amazon", "flipkart", "meesho"]
    assert data_all["generated"] >= 3
