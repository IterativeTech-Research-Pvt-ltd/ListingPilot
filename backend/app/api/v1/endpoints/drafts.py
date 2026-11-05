import json
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.config import settings
from app.models.product import Product
from app.models.draft import ListingDraft
from app.schemas.product import ProductResponse
from app.services.ai_service import AIService
from app.services.rule_engine import RuleEngine
from app.services.amazon_adapter import AmazonAdapter
from app.services.flipkart_adapter import FlipkartAdapter
from app.services.meesho_adapter import MeeshoAdapter, MeeshoExportIncomplete, MEESHO_CATEGORY_ATTR, BREADCRUMB_SEP
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


def _drafts_by_product(db: Session, products: List[Product], marketplace: Optional[str] = None) -> Dict[tuple, ListingDraft]:
    """{(product_id, marketplace): draft} in one query; a query per product takes ~0.4 s each to the remote database."""
    ids = [p.id for p in products]
    if not ids:
        return {}
    query = db.query(ListingDraft).filter(ListingDraft.product_id.in_(ids))
    if marketplace:
        query = query.filter(ListingDraft.marketplace == marketplace)
    return {(d.product_id, d.marketplace): d for d in query.all()}


# ── Single Product Draft Generation ──────────────────────────────────────────

@router.post("/generate/{product_id}", summary="Generate AI listing content & run rule checks (GEN-1 - GEN-4, RUL-1 - RUL-5)")
async def generate_draft(
    product_id: int,
    marketplace: str = Query("amazon", pattern="^(amazon|flipkart|meesho)$"),
    preview: bool = Query(False, description="Return new content without saving it when a draft already exists"),
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

    if preview and draft:
        # Keep the saved draft untouched; the editor shows this until the user saves or approves it
        return {
            **draft.to_dict(),
            "title": content["title"],
            "bullets": content["bullets"],
            "description": content["description"],
            "keywords": content["keywords"],
            "technical_specs": content.get("technical_specs", {}),
            "aplus_content": content.get("aplus_content", {}),
            "status": status,
            "is_approved": False,
            "rule_results": rule_results,
            "generation_source": AIService.generation_source(content),
            "preview": True,
        }

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
    # Not persisted (no column yet): tells the UI whether AI or the template generator wrote this
    return {**draft.to_dict(), "generation_source": AIService.generation_source(content)}


# ── Batch Draft Generation ───────────────────────────────────────────────────

@router.post("/generate-batch", summary="Generate AI drafts for all (or filtered) products in batch")
async def generate_batch(
    request: Request,
    marketplace: str = Query("amazon", pattern="^(amazon|flipkart|meesho|all)$"),
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
    template_items = []
    cancelled = False
    target_marketplaces = ["amazon", "flipkart", "meesho"] if marketplace == "all" else [marketplace]

    for product in products:
        if cancelled:
            break
        for mp in target_marketplaces:
            # Stop generating once the client cancels (aborted fetch / closed tab)
            if await request.is_disconnected():
                print(f"Batch generation cancelled by client after {generated} drafts")
                cancelled = True
                break

            # Check if draft already exists
            existing = db.query(ListingDraft).filter(
                ListingDraft.product_id == product.id,
                ListingDraft.marketplace == mp
            ).first()

            if existing and not overwrite:
                skipped += 1
                continue

            try:
                content = await AIService.generate_listing(product, marketplace=mp)
                rule_results = RuleEngine.evaluate(product, draft=content, marketplace=mp)
                status = "draft"

                if existing:
                    existing.title = content["title"]
                    existing.bullets = content["bullets"]
                    existing.description = content["description"]
                    existing.keywords = content["keywords"]
                    existing.technical_specs = content.get("technical_specs", {})
                    existing.aplus_content = content.get("aplus_content", {})
                    existing.status = status
                    existing.is_approved = False
                    existing.rule_results = rule_results
                else:
                    draft = ListingDraft(
                        product_id=product.id,
                        marketplace=mp,
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

                generated += 1
                if AIService.generation_source(content) == "template":
                    template_items.append({"product_id": product.id, "sku": product.sku, "marketplace": mp})
            except Exception as e:
                errors_list.append({"product_id": product.id, "sku": product.sku, "marketplace": mp, "error": str(e)})

    db.commit()

    ai_generated = generated - len(template_items)
    return {
        "success": True,
        "cancelled": cancelled,
        "marketplace": marketplace,
        "marketplaces": target_marketplaces,
        "total_products": len(products),
        "generated": generated,
        "ai_generated": ai_generated,
        "template_generated": len(template_items),
        "template_items": template_items,
        "skipped": skipped,
        "errors": errors_list,
        "message": (
            f"Batch generation complete: {generated} drafts generated across {len(target_marketplaces)} channel(s) "
            f"({ai_generated} by AI, {len(template_items)} template copy), {skipped} skipped, {len(errors_list)} errors."
        )
    }


# ── Asynchronous Background Tasks (Celery + Redis / Multi-Tenant) ─────────────

@router.post("/tasks/generate-batch", summary="Dispatch background AI batch generation (Celery/Redis)")
def dispatch_generate_batch_task(
    marketplace: str = Query("amazon", pattern="^(amazon|flipkart|meesho|all)$"),
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
        pre_check = RuleEngine.evaluate(product, draft=None, marketplace=marketplace)
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


def _refresh_rule_results(db: Session, draft: ListingDraft) -> None:
    """Re-runs the rule checks on a draft against its product's current data (not committed here)."""
    product = db.query(Product).filter(Product.id == draft.product_id).first()
    draft.rule_results = RuleEngine.evaluate(product, draft={
        "title": draft.title, "bullets": draft.bullets, "description": draft.description, "keywords": draft.keywords,
    }, marketplace=draft.marketplace)


# ── Approval & Rejection ────────────────────────────────────────────────────

@router.post("/{draft_id}/approve", summary="Human approval for draft (WF-2)")
def approve_draft(
    draft_id: int,
    db: Session = Depends(get_db)
):
    draft = db.query(ListingDraft).filter(ListingDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Checked again against the product as it is now: its data (or Meesho category) may have changed since
    _refresh_rule_results(db, draft)
    errors = [i["message"] for i in draft.rule_results["issues"] if i["level"] == "error"]
    if errors:
        db.commit()  # keep the fresh results, so the editor shows what blocks approval
        raise HTTPException(
            status_code=400,
            detail="Cannot approve until these are fixed: " + " ".join(errors[:5])
                   + (f" (and {len(errors) - 5} more)" if len(errors) > 5 else "")
        )

    draft.is_approved = True
    draft.status = "approved"
    draft.rejection_reason = None  # fixed and approved again: an earlier rejection or Meesho QC reason no longer applies
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
        # Meesho has no listing API: nothing is published from here and no ID exists until Meesho assigns one
        raise HTTPException(status_code=409, detail=(
            "Meesho listings can't be published from ListingPilot. Download the Meesho sheet "
            "(Multi-Channel Hub), upload it at supplier.meesho.com > Catalog Upload > Bulk, and Meesho "
            "assigns the listing after its QC."
        ))
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
    drafts = _drafts_by_product(db, products)

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
            draft = drafts.get((product.id, mp))

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

def _meesho_items(db: Session, category: Optional[str], product_ids: Optional[str]) -> List[Dict[str, Any]]:
    """
    The products of one Meesho upload, each with its Meesho draft: the selected product ids when
    given (an id that doesn't exist is an error, never dropped), else a category, else every product.
    """
    query = db.query(Product)
    if product_ids is not None:
        try:
            ids = [int(x) for x in product_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=422, detail="product_ids must be comma-separated product ids.")
        if not ids:
            raise HTTPException(status_code=422, detail="No products selected for the Meesho upload.")
        products = query.filter(Product.id.in_(ids)).order_by(Product.id.asc()).all()
        unknown = sorted(set(ids) - {p.id for p in products})
        if unknown:
            raise HTTPException(status_code=404, detail=f"Products not found: {', '.join(map(str, unknown))}.")
    else:
        if category and category != "All":
            query = query.filter(Product.category == category)
        products = query.order_by(Product.id.asc()).all()
    if not products:
        raise HTTPException(status_code=404, detail="No products found for the Meesho upload.")
    drafts = _drafts_by_product(db, products, "meesho")
    items = []
    for prod in products:
        draft = drafts.get((prod.id, "meesho"))
        items.append({"product": prod, "draft": draft.to_dict() if draft else None})
    return items


@router.get("/meesho/export", summary="Export pre-filled Meesho Bulk Catalog Excel sheet (MSH-1)")
def export_meesho_catalog(
    product_ids: Optional[str] = Query(None, description="Comma-separated ids of the products in this upload"),
    category: Optional[str] = Query(None, description="Category filter, when no products are selected"),
    as_zip: bool = Query(False, description="Package multiple categories as a .zip file"),
    db: Session = Depends(get_db)
):
    """All or nothing: the file is made only when every product in the upload passes every check."""
    items = _meesho_items(db, category, product_ids)
    try:
        buf, media_type, filename = MeeshoAdapter.generate_batch_export(items, force_zip=as_zip)
    except MeeshoExportIncomplete as e:
        # No file at all rather than one Meesho rejects or that carries values we made up
        skus = {p["sku"] for p in e.problems if p["blocking"]}
        raise HTTPException(status_code=422, detail={
            "message": f"Meesho export blocked: {len(skus)} of {len(items)} product(s) aren't ready. "
                       f"Fix them or take them out of this upload.",
            "problems": e.problems,
        })
    # Exported, never "live": Meesho hasn't accepted anything until its processed file says so
    now = datetime.now(timezone.utc)
    for draft in _drafts_by_product(db, [item["product"] for item in items], "meesho").values():
        draft.status = "exported"
        draft.last_sync_at = now
    db.commit()
    SettingsService.record_sync("meesho")
    return StreamingResponse(
        buf,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/meesho/readiness", summary="Whether each product of a Meesho upload passes the export's checks")
def meesho_readiness(
    product_ids: Optional[str] = Query(None, description="Comma-separated ids of the products in this upload; all products when omitted"),
    db: Session = Depends(get_db)
):
    """
    Each product with its Meesho category and its blocking problems, by the export's own checks.
    Checked together, as the upload would be: two products sharing a Product Name both show it.
    """
    items = _meesho_items(db, None, product_ids)
    by_sku = MeeshoAdapter.check_items(items)
    rows = []
    for item in items:
        product = item["product"]
        tmpl, _ = MeeshoAdapter.resolve_item_template(item)
        problems = by_sku.get(product.sku, [])
        rows.append({
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "meesho_category": tmpl["breadcrumb"] if tmpl else None,
            "ready": not problems,
            "problems": [{"field": p["field"], "reason": p["reason"]} for p in problems],
            # Why Meesho's QC failed it last time (from an imported processed file), until it's approved again
            "qc_reason": (item["draft"] or {}).get("rejection_reason"),
        })
    return {"products": rows, "ready": sum(1 for r in rows if r["ready"]), "total": len(rows)}


MAX_PROCESSED_FILE_BYTES = 10 * 1024 * 1024


@router.post("/meesho/processed-file", summary="Import a processed (error or warning) file from the supplier panel")
async def import_meesho_processed_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Reads Meesho's processed file (ERROR STATUS / ERROR MESSAGE per SKU). Each failed product's Meesho draft
    goes back to unapproved with "Meesho QC: <message>" as its reason, so it can't be exported again until
    it's fixed and approved; the words Meesho flagged are learned, so new copy and checks avoid them.
    A file that can't be read changes nothing; SKUs not in the catalogue are reported, never dropped quietly.
    """
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Upload the .xlsx error or warning file downloaded from the supplier panel.")
    content = await file.read(MAX_PROCESSED_FILE_BYTES + 1)
    if len(content) > MAX_PROCESSED_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The file is over 10 MB; a Meesho processed file is far smaller.")
    try:
        rows = MeeshoAdapter.parse_processed_file(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not rows:
        raise HTTPException(status_code=422, detail="The file has no product rows (no SKU ID filled in).")

    # Learned first, so the failed drafts' checks below already flag the words
    learned = SettingsService.add_meesho_learned_words([k for r in rows if not r["passed"] for k in r["keywords"]])
    products = {p.sku: p for p in db.query(Product).filter(Product.sku.in_([r["sku"] for r in rows])).all()}
    drafts = _drafts_by_product(db, list(products.values()), "meesho")
    failed, passed, unknown = [], [], []
    for r in rows:
        product = products.get(r["sku"])
        if not product:
            unknown.append(r["sku"])
            continue
        if r["passed"]:
            passed.append({"product_id": product.id, "sku": product.sku})
            continue
        entry = {"product_id": product.id, "sku": product.sku, "status": r["status"], "message": r["message"],
                 "keywords": r["keywords"]}
        draft = drafts.get((product.id, "meesho"))
        if draft:
            draft.is_approved = False
            draft.status = "draft"
            draft.rejection_reason = f"Meesho QC: {r['message'] or r['status']}"
            _refresh_rule_results(db, draft)  # the editor shows the flagged words at once
        else:
            entry["note"] = "no Meesho draft to mark"
        failed.append(entry)
    db.commit()
    print(f"[MeeshoQC] Imported {file.filename}: {len(failed)} failed, {len(passed)} passed, "
          f"{len(unknown)} unknown SKU(s), {len(learned)} new flagged word(s)", flush=True)
    return {"rows": len(rows), "failed": failed, "passed": passed, "unknown_skus": unknown, "learned_words": learned,
            "flagged_words": MeeshoAdapter.flagged_words()}


@router.get("/meesho/fill-in-sheet", summary="Download the Meesho fields each product is missing, ready to fill and re-import")
def meesho_fill_in_sheet(
    product_ids: Optional[str] = Query(None, description="Comma-separated ids of the products in this upload"),
    category: Optional[str] = Query(None, description="Category filter, when no products are selected"),
    db: Session = Depends(get_db)
):
    items = _meesho_items(db, category, product_ids)
    buf = MeeshoAdapter.build_fill_in_sheet(items)
    if buf is None:
        raise HTTPException(status_code=404, detail="Nothing to fill: these products have every compulsory Meesho field.")
    safe_cat = re.sub(r"[^a-zA-Z0-9_-]", "_", "Selection" if product_ids is not None else (category or "All"))
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Meesho_fill_in_{safe_cat}.xlsx"'}
    )


def _meesho_missing(db: Session, product: Product) -> Dict[str, Any]:
    draft = _drafts_by_product(db, [product], "meesho").get((product.id, "meesho"))
    return MeeshoAdapter.missing_fields({"product": product, "draft": draft.to_dict() if draft else None})


class MeeshoFieldValues(BaseModel):
    values: Dict[str, str]


@router.get("/meesho/missing-fields/{product_id}", summary="Compulsory Meesho fields this product still lacks, with the template's options")
def get_meesho_missing_fields(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _meesho_missing(db, product)


@router.put("/meesho/missing-fields/{product_id}", summary="Save seller-entered Meesho fields into the product's attributes")
def save_meesho_missing_fields(product_id: int, payload: MeeshoFieldValues, db: Session = Depends(get_db)):
    """
    Merges the given values into the product's attributes (other attributes are untouched).
    Each key must be one of the product's template's fields, and a dropdown value must be one of the
    template's options exactly as spelled; otherwise nothing is saved. 'Meesho Category' picks the
    template: an official template's id or breadcrumb, saved as the id; empty removes the product's
    own choice so its category's default applies.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    tmpl, _ = MeeshoAdapter.resolve_item_template({"product": product})
    allowed = MeeshoAdapter.seller_fields(tmpl)

    errors, clean, removed = [], {}, set()
    for attr, value in payload.values.items():
        value = (value or "").strip()
        spec = allowed.get(attr)
        if attr == MEESHO_CATEGORY_ATTR:
            entry = MeeshoAdapter.template_by_ref(value)
            if not value:
                removed.add(attr)
            elif entry:
                clean[attr] = entry["id"]
            else:
                errors.append(f"'{value}' is not an official Meesho category")
        elif spec is None:
            errors.append(f"'{attr}' is not a field of the {tmpl['category'] if tmpl else product.category} template"
                          + ("" if tmpl else f"; set '{MEESHO_CATEGORY_ATTR}' first"))
        elif not value:
            errors.append(f"'{attr}' is empty")
        elif spec["options"] and value not in spec["options"]:
            errors.append(f"'{value}' is not one of the template's options for '{spec['field']}'")
        else:
            clean[attr] = value
    if errors or not (clean or removed):
        raise HTTPException(status_code=422, detail={"message": "Nothing saved.", "errors": errors or ["No values given."]})

    # A new dict, so SQLAlchemy sees the JSON column change
    kept = {k: v for k, v in (product.attributes or {}).items() if k.strip().lower() not in {r.lower() for r in removed}}
    product.attributes = {**kept, **clean}
    # The Meesho draft's checks read these fields: refresh them so approval reflects the saved values
    draft = _drafts_by_product(db, [product], "meesho").get((product.id, "meesho"))
    if draft:
        _refresh_rule_results(db, draft)
    db.commit()
    db.refresh(product)
    return {
        "product": ProductResponse.model_validate(product).model_dump(mode="json"),
        "missing": _meesho_missing(db, product),
        "draft": draft.to_dict() if draft else None,
    }


@router.get("/meesho/category-fields/{template_id}", summary="The fields the Add Product form asks for a Meesho category")
def get_meesho_category_fields(template_id: str):
    entry = MeeshoAdapter.template_by_ref(template_id) if template_id.isdigit() else None
    if not entry:
        raise HTTPException(status_code=404, detail=f"No Meesho template has the id '{template_id}'.")
    tmpl = MeeshoAdapter._load_template(entry)
    if not tmpl:
        raise HTTPException(status_code=500, detail=f"The Meesho template file for {entry['breadcrumb']} couldn't be read.")
    return {"id": entry["id"], "breadcrumb": entry["breadcrumb"], "fields": MeeshoAdapter.category_fields(tmpl)}


@router.get("/meesho/taxonomy", summary="Meesho's category tree (4 levels), each leaf with its template id")
def get_meesho_taxonomy():
    """The same tree as the supplier panel's Bulk Catalog Upload, for the category picker."""
    return {"separator": BREADCRUMB_SEP, "tree": MeeshoAdapter.taxonomy_tree()}


class MeeshoCategoryDefault(BaseModel):
    category: str
    meesho_category: Optional[str] = None  # template id or breadcrumb; empty clears the default


def _meesho_category_defaults(db: Session) -> List[Dict[str, Any]]:
    """Every seller category (with its product count) and the Meesho category chosen for it, if any."""
    counts = dict(db.query(Product.category, func.count(Product.id)).group_by(Product.category).all())
    saved = SettingsService.get_meesho_category_defaults()
    rows = []
    for category in sorted(set(counts) | set(saved), key=lambda c: (c or "").lower()):
        entry = MeeshoAdapter.template_by_ref(saved.get(category))
        rows.append({
            "category": category,
            "products": counts.get(category, 0),
            "id": entry["id"] if entry else None,
            "breadcrumb": entry["breadcrumb"] if entry else None,
            # A saved id that no longer names a template is shown, not hidden
            "invalid_value": saved.get(category) if saved.get(category) and not entry else None,
            # Templates the category's name could mean, offered in the picker; never saved unasked
            "suggestions": [{"id": c["id"], "breadcrumb": c["breadcrumb"]} for c in MeeshoAdapter.template_candidates(category)][:8],
        })
    return rows


@router.get("/meesho/category-defaults", summary="The Meesho category chosen for each seller category")
def get_meesho_category_defaults(db: Session = Depends(get_db)):
    return {"defaults": _meesho_category_defaults(db)}


@router.put("/meesho/category-defaults", summary="Choose (or clear) the Meesho category for every product in a seller category")
def set_meesho_category_default(payload: MeeshoCategoryDefault, db: Session = Depends(get_db)):
    """A product's own 'Meesho Category' still wins over its category's default."""
    category = (payload.category or "").strip()
    if not category:
        raise HTTPException(status_code=422, detail="Category is required.")
    value = (payload.meesho_category or "").strip()
    entry = MeeshoAdapter.template_by_ref(value) if value else None
    if value and not entry:
        raise HTTPException(status_code=422, detail=f"'{value}' is not an official Meesho category.")
    SettingsService.set_meesho_category_default(category, entry["id"] if entry else None)
    return {"defaults": _meesho_category_defaults(db)}


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
