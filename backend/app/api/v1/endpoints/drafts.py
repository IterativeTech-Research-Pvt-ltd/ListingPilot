from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.config import settings
from app.models.product import Product
from app.models.draft import ListingDraft
from app.services.ai_service import AIService
from app.services.rule_engine import RuleEngine
from app.services.amazon_adapter import AmazonAdapter
from app.services.flipkart_adapter import FlipkartAdapter
from app.services.meesho_adapter import MeeshoAdapter
from app.services.settings_service import SettingsService
from app.tasks.batch_tasks import (
    generate_batch_drafts_task,
    publish_batch_drafts_task,
    get_celery_task_status,
)
from app.core.celery_app import celery_app
from fastapi.responses import StreamingResponse

router = APIRouter()

class DraftUpdateRequest(BaseModel):
    title: Optional[str] = None
    bullets: Optional[List[str]] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    technical_specs: Optional[Dict[str, Any]] = None
    aplus_content: Optional[Dict[str, Any]] = None

class RejectRequest(BaseModel):
    reason: str


# ── Single Product Draft Generation ──────────────────────────────────────────

@router.post("/generate/{product_id}", summary="Generate AI listing content & run rule checks (GEN-1 - GEN-4, RUL-1 - RUL-5)")
async def generate_draft(
    product_id: int,
    marketplace: str = Query("amazon", pattern="^(amazon|flipkart|meesho)$"),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Call AI generation service
    content = await AIService.generate_listing(product, marketplace=marketplace)
    
    # Run rule evaluation
    rule_results = RuleEngine.evaluate(product, draft=content, marketplace=marketplace)
    
    # Determine status: starts in draft state (issues are captured in rule_results)
    status = "draft"

    # Upsert draft
    draft = db.query(ListingDraft).filter(
        ListingDraft.product_id == product_id,
        ListingDraft.marketplace == marketplace
    ).first()

    if draft:
        draft.title = content["title"]
        draft.bullets = content["bullets"]
        draft.description = content["description"]
        draft.keywords = content["keywords"]
        draft.technical_specs = content.get("technical_specs", {})
        draft.aplus_content = content.get("aplus_content", {})
        draft.status = status
        draft.is_approved = False  # Reset approval on regeneration
        draft.rule_results = rule_results
    else:
        draft = ListingDraft(
            product_id=product_id,
            marketplace=marketplace,
            title=content["title"],
            bullets=content["bullets"],
            description=content["description"],
            keywords=content["keywords"],
            technical_specs=content.get("technical_specs", {}),
            aplus_content=content.get("aplus_content", {}),
            status=status,
            is_approved=False,
            rule_results=rule_results
        )
        db.add(draft)

    db.commit()
    db.refresh(draft)
    return draft.to_dict()


# ── Batch Draft Generation ───────────────────────────────────────────────────

@router.post("/generate-batch", summary="Generate AI drafts for all (or filtered) products in batch")
async def generate_batch(
    marketplace: str = Query("amazon", pattern="^(amazon|flipkart|meesho)$"),
    category: Optional[str] = Query(None, description="Filter by category"),
    overwrite: bool = Query(False, description="Re-generate existing drafts"),
    db: Session = Depends(get_db)
):
    """
    Generate AI listing content for all products (or a category subset).
    Skips products that already have a draft unless overwrite=True.
    Returns a summary of the batch operation.
    """
    query = db.query(Product)
    if category and category != "All":
        query = query.filter(Product.category == category)
    products = query.order_by(Product.id.asc()).all()

    if not products:
        raise HTTPException(status_code=404, detail="No products found for the given filter.")

    generated = 0
    skipped = 0
    errors_list = []

    for product in products:
        # Check if draft already exists
        existing = db.query(ListingDraft).filter(
            ListingDraft.product_id == product.id,
            ListingDraft.marketplace == marketplace
        ).first()

        if existing and not overwrite:
            skipped += 1
            continue

        try:
            content = await AIService.generate_listing(product, marketplace=marketplace)
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
            errors_list.append({"product_id": product.id, "sku": product.sku, "error": str(e)})

    db.commit()

    return {
        "success": True,
        "marketplace": marketplace,
        "total_products": len(products),
        "generated": generated,
        "skipped": skipped,
        "errors": errors_list,
        "message": f"Batch generation complete: {generated} drafts generated, {skipped} skipped, {len(errors_list)} errors."
    }


# ── Asynchronous Background Tasks (Celery + Redis / Multi-Tenant) ─────────────

@router.post("/tasks/generate-batch", summary="Dispatch background AI batch generation (Celery/Redis)")
def dispatch_generate_batch_task(
    marketplace: str = Query("amazon", pattern="^(amazon|flipkart|meesho)$"),
    category: Optional[str] = Query(None, description="Filter by category"),
    overwrite: bool = Query(False, description="Re-generate existing drafts"),
    tenant_id: Optional[str] = Query(None, description="Tenant / Brand ID for multi-tenant isolation"),
):
    """
    Dispatches long-running AI batch generation to background Celery workers.
    Returns immediately with a task_id for non-blocking UI and multi-tenant queuing.
    """
    task = generate_batch_drafts_task.delay(
        marketplace=marketplace,
        category=category,
        overwrite=overwrite,
        tenant_id=tenant_id
    )
    return {
        "task_id": task.id,
        "status": "QUEUED",
        "marketplace": marketplace,
        "tenant_id": tenant_id,
        "check_status_url": f"/api/v1/drafts/tasks/{task.id}"
    }


@router.get("/tasks/{task_id}", summary="Check status & real-time progress of a background Celery task")
def check_task_status(task_id: str):
    """
    Polls the status, percentage progress, and completion payload of any Celery task.
    """
    return get_celery_task_status(task_id)


@router.post("/tasks/publish-batch", summary="Dispatch background batch publish to marketplaces")
def dispatch_publish_batch_task(
    draft_ids: List[int],
    marketplace: str = Query("amazon", pattern="^(amazon|flipkart|meesho)$"),
    tenant_id: Optional[str] = Query(None, description="Tenant / Brand ID for multi-tenant isolation"),
):
    """
    Dispatches batch marketplace publishing to background Celery workers.
    """
    task = publish_batch_drafts_task.delay(
        draft_ids=draft_ids,
        marketplace=marketplace,
        tenant_id=tenant_id
    )
    return {
        "task_id": task.id,
        "status": "QUEUED",
        "marketplace": marketplace,
        "tenant_id": tenant_id,
        "check_status_url": f"/api/v1/drafts/tasks/{task.id}"
    }


# ── Single Draft CRUD ────────────────────────────────────────────────────────

@router.get("/product/{product_id}", summary="Get draft for a specific product")
def get_product_draft(
    product_id: int,
    marketplace: str = Query("amazon"),
    db: Session = Depends(get_db)
):
    draft = db.query(ListingDraft).filter(
        ListingDraft.product_id == product_id,
        ListingDraft.marketplace == marketplace
    ).first()
    if not draft:
        # If no draft yet, return pre-check for master catalogue data
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        pre_check = RuleEngine.evaluate(product, draft=None)
        return {
            "id": None,
            "product_id": product_id,
            "marketplace": marketplace,
            "title": "",
            "bullets": [],
            "description": "",
            "keywords": [],
            "status": "not_generated",
            "is_approved": False,
            "rule_results": pre_check
        }
    return draft.to_dict()


@router.put("/{draft_id}", summary="Edit draft content - re-runs rule checks (WF-2)")
def update_draft(
    draft_id: int,
    req: DraftUpdateRequest,
    db: Session = Depends(get_db)
):
    draft = db.query(ListingDraft).filter(ListingDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    product = db.query(Product).filter(Product.id == draft.product_id).first()

    if req.title is not None: draft.title = req.title
    if req.bullets is not None: draft.bullets = req.bullets
    if req.description is not None: draft.description = req.description
    if req.keywords is not None: draft.keywords = req.keywords
    if req.technical_specs is not None: draft.technical_specs = req.technical_specs
    if req.aplus_content is not None: draft.aplus_content = req.aplus_content

    # Re-evaluate rules after human edit
    draft_dict = {
        "title": draft.title,
        "bullets": draft.bullets,
        "description": draft.description,
        "keywords": draft.keywords
    }
    rule_results = RuleEngine.evaluate(product, draft=draft_dict, marketplace=draft.marketplace)
    draft.rule_results = rule_results
    draft.is_approved = False  # Reset approval on edit per SRS section 5

    draft.status = "draft"

    db.commit()
    db.refresh(draft)
    return draft.to_dict()


# ── Approval & Rejection ────────────────────────────────────────────────────

@router.post("/{draft_id}/approve", summary="Human approval for draft (WF-2)")
def approve_draft(
    draft_id: int,
    db: Session = Depends(get_db)
):
    draft = db.query(ListingDraft).filter(ListingDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Verify that the draft has no blocking errors
    if draft.rule_results and draft.rule_results.get("has_errors"):
        raise HTTPException(
            status_code=400,
            detail="Cannot approve a draft with unresolved rule check errors. Fix the issues first."
        )

    draft.is_approved = True
    draft.status = "approved"
    db.commit()
    db.refresh(draft)
    return draft.to_dict()


@router.post("/{draft_id}/reject", summary="Manually reject a draft with a reason")
def reject_draft(
    draft_id: int,
    req: RejectRequest,
    db: Session = Depends(get_db)
):
    draft = db.query(ListingDraft).filter(ListingDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft.status = "draft"
    draft.is_approved = False
    draft.rejection_reason = req.reason
    db.commit()
    db.refresh(draft)
    return draft.to_dict()


# ── Publish to Marketplace ───────────────────────────────────────────────────

@router.post("/{draft_id}/publish", summary="Publish approved draft to marketplace (AMZ-1)")
async def publish_draft(
    draft_id: int,
    db: Session = Depends(get_db)
):
    """
    Publishes an approved draft to its target marketplace.
    Only approved drafts can be published (WF-2).
    Currently supports Amazon (stub adapter); Flipkart and Meesho in Phase 3.
    """
    draft = db.query(ListingDraft).filter(ListingDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if not draft.is_approved or draft.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Only approved drafts can be published. Approve the draft first."
        )

    product = db.query(Product).filter(Product.id == draft.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Associated product not found")

    # Status remains approved during submission

    draft_data = {
        "title": draft.title,
        "bullets": draft.bullets,
        "description": draft.description,
        "keywords": draft.keywords,
        "technical_specs": draft.technical_specs or {},
        "aplus_content": draft.aplus_content or {},
    }
    product_data = product.to_dict()

    if draft.marketplace == "amazon":
        result = await AmazonAdapter.create_listing(draft_data, product_data)
    elif draft.marketplace == "flipkart":
        result = await FlipkartAdapter.create_listing(draft_data, product_data)
    elif draft.marketplace == "meesho":
        # For Meesho, publishing assigns external ID and certifies the item for bulk catalog export
        result = {
            "success": True,
            "marketplace": "meesho",
            "sku": product.sku,
            "external_listing_id": f"MSH-{product.sku}",
            "status": "live",
            "message": "Packaged and ready in Meesho bulk catalog upload sheet."
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown marketplace: {draft.marketplace}")

    # Update draft based on adapter response
    if result.get("success"):
        draft.status = "live"
        draft.external_listing_id = result.get("external_listing_id")
        draft.marketplace_sku = product.sku
        draft.last_sync_at = datetime.now(timezone.utc)
        draft.rejection_reason = None
        SettingsService.record_sync(draft.marketplace)
    else:
        draft.status = "draft"
        draft.is_approved = False
        draft.rejection_reason = result.get("rejection_reason", "Unknown marketplace error")

    db.commit()
    db.refresh(draft)

    return {
        "draft": draft.to_dict(),
        "publish_result": result,
    }


@router.get("/{draft_id}/amazon-payload", summary="Preview official Amazon SP-API Listings Items 2021-08-01 payload")
def get_amazon_sp_api_payload(
    draft_id: int,
    db: Session = Depends(get_db)
):
    """
    Constructs and returns the authentic Amazon SP-API Listings Items (2021-08-01)
    JSON payload, incorporating copy, category PTD attributes, dimensions,
    and Indian Legal Metrology compliance data.
    """
    draft = db.query(ListingDraft).filter(ListingDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    product = db.query(Product).filter(Product.id == draft.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Associated product not found")

    sp_payload = AmazonAdapter.build_sp_api_listing_payload(
        draft_data=draft.to_dict(),
        product_data=product.to_dict()
    )

    return {
        "draft_id": draft.id,
        "product_id": product.id,
        "sku": product.sku,
        "marketplace": "amazon",
        "marketplace_id": settings.AMAZON_MARKETPLACE_ID,
        "sp_api_spec": "Listings Items API v2021-08-01",
        "product_type": sp_payload.get("productType"),
        "payload": sp_payload
    }


@router.get("/{draft_id}/aplus-payload", summary="Preview official Amazon A+ Content (EBC) API 2020-11-01 payload")
def get_amazon_aplus_payload(
    draft_id: int,
    db: Session = Depends(get_db)
):
    """
    Constructs and returns the authentic Amazon A+ Content (EBC) API (2020-11-01)
    JSON document, featuring brand storytelling, 3 feature spotlight cards,
    and the flagship Apple-style multi-model comparison matrix.
    """
    draft = db.query(ListingDraft).filter(ListingDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    product = db.query(Product).filter(Product.id == draft.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Associated product not found")

    aplus_payload = AmazonAdapter.build_aplus_content_payload(
        draft_data=draft.to_dict(),
        product_data=product.to_dict()
    )

    return {
        "draft_id": draft.id,
        "product_id": product.id,
        "sku": product.sku,
        "marketplace": "amazon",
        "marketplace_id": settings.AMAZON_MARKETPLACE_ID,
        "sp_api_spec": "A+ Content API v2020-11-01 (EBC)",
        "payload": aplus_payload
    }




# ── Marketplace Status ───────────────────────────────────────────────────────

@router.get("/marketplace-status", summary="Get per-SKU marketplace status grid (WF-3)")
def get_marketplace_status(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Returns per-product status across all marketplaces (WF-3).
    Shows which products are live where and which are stuck.
    """
    from sqlalchemy import or_
    query = db.query(Product)
    if category and category != "All":
        query = query.filter(Product.category == category)
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                Product.sku.ilike(term),
                Product.name.ilike(term),
            )
        )
    products = query.order_by(Product.id.asc()).all()

    result = []
    for product in products:
        row = {
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "image_count": product.image_count or 0,
            "marketplaces": {},
        }

        for mp in ["amazon", "flipkart", "meesho"]:
            draft = db.query(ListingDraft).filter(
                ListingDraft.product_id == product.id,
                ListingDraft.marketplace == mp
            ).first()

            if draft:
                row["marketplaces"][mp] = {
                    "draft_id": draft.id,
                    "status": draft.status,
                    "is_approved": draft.is_approved,
                    "external_listing_id": draft.external_listing_id,
                    "quality_score": (draft.rule_results or {}).get("score", 0),
                    "has_errors": (draft.rule_results or {}).get("has_errors", False),
                    "last_sync_at": draft.last_sync_at.isoformat() if draft.last_sync_at else None,
                    "rejection_reason": draft.rejection_reason,
                }
            else:
                row["marketplaces"][mp] = {
                    "draft_id": None,
                    "status": "not_started",
                    "is_approved": False,
                    "external_listing_id": None,
                    "quality_score": 0,
                    "has_errors": False,
                    "last_sync_at": None,
                    "rejection_reason": None,
                }

        result.append(row)

    return {
        "total": len(result),
        "items": result,
    }


# ── Meesho Bulk Catalog Sheet Export (MSH-1) ──────────────────────────────────

@router.get("/meesho/export", summary="Export pre-filled Meesho Bulk Catalog Excel sheet (MSH-1)")
def export_meesho_catalog(
    category: Optional[str] = Query(None, description="Category filter"),
    as_zip: bool = Query(False, description="Package multiple categories as a .zip file"),
    db: Session = Depends(get_db)
):
    query = db.query(Product)
    if category and category != "All":
        query = query.filter(Product.category == category)
    products = query.order_by(Product.id.asc()).all()

    if not products:
        raise HTTPException(status_code=404, detail="No products found to generate Meesho bulk catalog.")

    items = []
    for prod in products:
        draft = db.query(ListingDraft).filter(
            ListingDraft.product_id == prod.id,
            ListingDraft.marketplace == "meesho"
        ).first()
        items.append({
            "product": prod,
            "draft": draft.to_dict() if draft else None
        })

    buf, media_type, filename = MeeshoAdapter.generate_batch_export(items, category_filter=category, force_zip=as_zip)
    SettingsService.record_sync("meesho")
    return StreamingResponse(
        buf,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/meesho/templates", summary="List available official Meesho category templates")
def list_meesho_templates():
    """Returns all official Meesho .xlsx templates discovered in the templates directory."""
    templates = MeeshoAdapter.get_available_templates()
    return {
        "success": True,
        "count": len(templates),
        "templates": templates
    }


@router.get("/meesho/categories", summary="Search official Meesho categories taxonomy and template mapping")
def get_meesho_categories(
    search: Optional[str] = Query(None, description="Search term for Meesho category name or path"),
    limit: int = Query(50, description="Max categories to return (1-200)", ge=1, le=200)
):
    """Returns official Meesho leaf categories matching query, annotated with template readiness."""
    categories = MeeshoAdapter.get_categories(search=search, limit=limit)
    return {
        "success": True,
        "count": len(categories),
        "categories": categories
    }


# ── Unified Marketplace Credentials Status (ADM-3) ───────────────────────────

@router.get("/credentials-status", summary="Check connection status for all marketplaces (ADM-3)")
def get_all_credentials_status():
    return {
        "amazon": AmazonAdapter.validate_credentials(),
        "flipkart": FlipkartAdapter.validate_credentials(),
        "meesho": MeeshoAdapter.validate_credentials(),
    }


# ── Amazon Credentials Status ────────────────────────────────────────────────

@router.get("/amazon-status", summary="Check Amazon SP-API credentials status")
def amazon_credentials_status():
    return AmazonAdapter.validate_credentials()


# ── Draft Stats (Alias) ──────────────────────────────────────────────────────

@router.get("/stats", summary="Get draft pipeline stats summary")
def get_draft_stats_summary(db: Session = Depends(get_db)):
    total = db.query(func.count(ListingDraft.id)).scalar() or 0
    status_rows = (
        db.query(ListingDraft.status, func.count(ListingDraft.id))
        .group_by(ListingDraft.status)
        .all()
    )
    status_counts = {s: c for s, c in status_rows}
    all_drafts = db.query(ListingDraft).all()
    scores = [(d.rule_results or {}).get("score", 0) for d in all_drafts]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    return {
        "total_drafts": total,
        "status_counts": status_counts,
        "avg_quality_score": avg_score,
        "max_quality_score": 25,
    }


# ── List Drafts ──────────────────────────────────────────────────────────────

@router.get("", summary="List all drafts")
def list_drafts(
    marketplace: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(ListingDraft)
    if marketplace:
        query = query.filter(ListingDraft.marketplace == marketplace)
    if status:
        query = query.filter(ListingDraft.status == status)
    
    drafts = query.order_by(ListingDraft.updated_at.desc()).all()
    return [d.to_dict() for d in drafts]
