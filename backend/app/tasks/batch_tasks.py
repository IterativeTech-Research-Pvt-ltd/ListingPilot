"""
Celery Background Tasks (Multi-Tenant & Distributed Execution)
Handles asynchronous long-running jobs:
1. AI Batch Listing Generation with real-time progress tracking
2. Multi-channel Batch Publishing
3. Multi-tenant context scoping
"""
import asyncio
from typing import Dict, Any, List, Optional
from celery.result import AsyncResult
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.product import Product
from app.models.draft import ListingDraft
from app.services.ai_service import AIService
from app.services.rule_engine import RuleEngine
from app.services.amazon_adapter import AmazonAdapter
from app.services.flipkart_adapter import FlipkartAdapter
from app.services.meesho_adapter import MeeshoAdapter


def _run_async(coro):
    """Helper to run async coroutines safely inside synchronous Celery worker threads."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # In case Celery runs inside an existing event loop
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    return loop.run_until_complete(coro)


def get_task_db_session():
    """Returns a database session, respecting any test dependency overrides on get_db."""
    try:
        from app.main import app
        from app.core.database import get_db
        if get_db in app.dependency_overrides:
            override_gen = app.dependency_overrides[get_db]()
            return next(override_gen)
    except Exception:
        pass
    return SessionLocal()


@celery_app.task(bind=True, name="app.tasks.generate_batch_drafts")
def generate_batch_drafts_task(
    self,
    marketplace: str = "amazon",
    category: Optional[str] = None,
    product_ids: Optional[List[int]] = None,
    overwrite: bool = False,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Asynchronously generates AI listing drafts for a batch of products with progress tracking.
    Multi-tenant ready: scopes products and drafts to the tenant_id if specified.
    """
    db = get_task_db_session()
    try:
        query = db.query(Product)
        
        # Multi-tenant scoping: if tenant_id provided, filter products
        if tenant_id:
            # If tenant specifies brand or organization
            query = query.filter((Product.brand == tenant_id) | (Product.brand.ilike(f"%{tenant_id}%")))

        if product_ids:
            query = query.filter(Product.id.in_(product_ids))
        elif category and category != "All":
            query = query.filter(Product.category == category)

        products = query.order_by(Product.id.asc()).all()
        total = len(products)

        if total == 0:
            return {
                "success": True,
                "tenant_id": tenant_id,
                "marketplace": marketplace,
                "total_products": 0,
                "generated": 0,
                "skipped": 0,
                "errors": [],
                "message": "No products found matching task filter.",
            }

        generated = 0
        skipped = 0
        errors_list = []

        for idx, product in enumerate(products):
            # Update Celery task state with real-time percentage progress
            percent = round(((idx + 1) / total) * 100, 1)
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": idx + 1,
                    "total": total,
                    "percent": percent,
                    "current_sku": product.sku,
                    "marketplace": marketplace,
                    "tenant_id": tenant_id,
                }
            )

            existing = db.query(ListingDraft).filter(
                ListingDraft.product_id == product.id,
                ListingDraft.marketplace == marketplace
            ).first()

            if existing and not overwrite:
                skipped += 1
                continue

            try:
                # Generate AI listing content
                content = _run_async(AIService.generate_listing(product, marketplace=marketplace))
                rule_results = RuleEngine.evaluate(product, draft=content, marketplace=marketplace)
                status = "draft"

                if existing:
                    existing.title = content["title"]
                    existing.bullets = content["bullets"]
                    existing.description = content["description"]
                    existing.keywords = content["keywords"]
                    existing.status = status
                    existing.is_approved = False
                    existing.rule_results = rule_results
                else:
                    draft = ListingDraft(
                        product_id=product.id,
                        marketplace=marketplace,
                        title=content["title"],
                        bullets=content["bullets"],
                        description=content["description"],
                        keywords=content["keywords"],
                        status=status,
                        is_approved=False,
                        rule_results=rule_results
                    )
                    db.add(draft)

                generated += 1
            except Exception as e:
                errors_list.append({
                    "product_id": product.id,
                    "sku": product.sku,
                    "error": str(e)
                })

        db.commit()

        return {
            "success": True,
            "tenant_id": tenant_id,
            "marketplace": marketplace,
            "total_products": total,
            "generated": generated,
            "skipped": skipped,
            "errors": errors_list,
            "message": f"Batch generation complete for tenant '{tenant_id or 'default'}': {generated} generated, {skipped} skipped, {len(errors_list)} errors.",
        }
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.publish_batch_drafts")
def publish_batch_drafts_task(
    self,
    draft_ids: List[int],
    marketplace: str = "amazon",
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Asynchronously publishes a batch of approved drafts to marketplace adapters.
    """
    db = get_task_db_session()
    try:
        drafts = db.query(ListingDraft).filter(ListingDraft.id.in_(draft_ids)).all()
        total = len(drafts)
        published = 0
        failed = 0
        results = []

        for idx, draft in enumerate(drafts):
            percent = round(((idx + 1) / total) * 100, 1)
            self.update_state(
                state="PROGRESS",
                meta={"current": idx + 1, "total": total, "percent": percent}
            )

            if not draft.is_approved:
                failed += 1
                results.append({"draft_id": draft.id, "success": False, "error": "Draft is not approved."})
                continue

            product = db.query(Product).filter(Product.id == draft.product_id).first()
            if not product:
                failed += 1
                results.append({"draft_id": draft.id, "success": False, "error": "Product not found."})
                continue

            product_data = {
                "sku": product.sku,
                "price": product.price,
                "stock": product.stock,
                "images": product.images or [],
                "attributes": product.attributes or {},
            }
            draft_data = {
                "title": draft.title,
                "bullets": draft.bullets or [],
                "description": draft.description,
                "keywords": draft.keywords or [],
            }

            try:
                mp = (draft.marketplace or marketplace).lower()
                if mp == "amazon":
                    res = AmazonAdapter.create_listing(draft_data, product_data)
                elif mp == "flipkart":
                    res = FlipkartAdapter.create_listing(draft_data, product_data)
                elif mp == "meesho":
                    res = MeeshoAdapter.generate_bulk_upload_row(product, draft)
                else:
                    res = {"success": False, "error": f"Unsupported marketplace: {mp}"}

                if res.get("success", True):
                    draft.status = "live"
                    draft.external_listing_id = res.get("external_listing_id") or res.get("asin") or res.get("fsn")
                    published += 1
                    results.append({"draft_id": draft.id, "success": True, "external_id": draft.external_listing_id})
                else:
                    failed += 1
                    results.append({"draft_id": draft.id, "success": False, "error": res.get("rejection_reason") or "Failed"})
            except Exception as e:
                failed += 1
                results.append({"draft_id": draft.id, "success": False, "error": str(e)})

        db.commit()
        return {
            "success": True,
            "tenant_id": tenant_id,
            "marketplace": marketplace,
            "total": total,
            "published": published,
            "failed": failed,
            "details": results,
        }
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


def get_celery_task_status(task_id: str) -> Dict[str, Any]:
    """Inspects the execution state and progress of an async Celery task."""
    task_result = AsyncResult(task_id, app=celery_app)
    state = task_result.state
    
    response: Dict[str, Any] = {
        "task_id": task_id,
        "state": state,
        "ready": task_result.ready(),
        "successful": task_result.successful() if task_result.ready() else None,
    }

    if state == "PROGRESS":
        response["progress"] = task_result.info
    elif state == "SUCCESS":
        response["result"] = task_result.result
    elif state == "FAILURE":
        response["error"] = str(task_result.info)
    else:
        response["info"] = str(task_result.info)

    return response
