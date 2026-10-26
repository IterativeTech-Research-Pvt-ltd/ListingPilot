import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.celery_app import celery_app
from app.tasks.batch_tasks import (
    generate_batch_drafts_task,
    publish_batch_drafts_task,
    get_celery_task_status,
)

client = TestClient(app)


def test_celery_app_configuration():
    """Verify Celery app initializes with correct broker and task settings."""
    assert celery_app.main == "listingpilot"
    assert "app.tasks.generate_batch_drafts" in celery_app.tasks
    assert "app.tasks.publish_batch_drafts" in celery_app.tasks


def test_dispatch_generate_batch_task_endpoint():
    """Test dispatching an asynchronous AI batch generation task via API."""
    response = client.post("/api/v1/drafts/tasks/generate-batch?marketplace=amazon&tenant_id=Gulmohar%20Home")
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] in ("QUEUED", "SUCCESS")
    assert data["marketplace"] == "amazon"
    assert data["tenant_id"] == "Gulmohar Home"
    assert f"/api/v1/drafts/tasks/{data['task_id']}" in data["check_status_url"]


def test_poll_task_status_endpoint():
    """Test polling the status of a Celery background task."""
    # Run task (eager execution in test env)
    task = generate_batch_drafts_task.delay(marketplace="flipkart", tenant_id="Gulmohar Home")
    assert task.id is not None

    response = client.get(f"/api/v1/drafts/tasks/{task.id}")
    assert response.status_code == 200
    status_data = response.json()
    assert status_data["task_id"] == task.id
    assert status_data["state"] in ("SUCCESS", "PROGRESS", "PENDING")


def test_multi_tenant_scoping_in_task():
    """Verify that tenant_id properly scopes task execution without cross-tenant interference."""
    # Task with a non-existent tenant should find 0 products and succeed safely
    result = generate_batch_drafts_task(marketplace="amazon", tenant_id="NonExistentTenant999")
    assert result["success"] is True
    assert result["tenant_id"] == "NonExistentTenant999"
    assert result["total_products"] == 0
