"""
Reports & Baseline Metrics API (RPT-1)
Provides data for measuring listing time, quality, and rejection rates.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.product import Product
from app.models.draft import ListingDraft

router = APIRouter()


@router.get("/baseline", summary="Get baseline metrics for pilot comparison (RPT-1)")
def get_baseline_metrics(db: Session = Depends(get_db)):
    """
    Returns key metrics to compare current (manual) listing process
    against ListingPilot's automated results.
    """
    total_products = db.query(func.count(Product.id)).scalar() or 0
    total_drafts = db.query(func.count(ListingDraft.id)).scalar() or 0

    # Status breakdown
    status_counts = {}
    status_rows = (
        db.query(ListingDraft.status, func.count(ListingDraft.id))
        .group_by(ListingDraft.status)
        .all()
    )
    for status, count in status_rows:
        status_counts[status] = count

    # Products with at least one draft
    products_with_drafts = (
        db.query(func.count(func.distinct(ListingDraft.product_id))).scalar() or 0
    )

    all_drafts = db.query(ListingDraft).all()

    # Approval and lifecycle counts
    draft_count = status_counts.get("draft", 0)
    approved_count = status_counts.get("approved", 0)
    live_count = status_counts.get("live", 0)
    rejected_count = sum(1 for d in all_drafts if getattr(d, 'rejection_reason', None))

    # Quality score distribution
    scores = []
    quality_distribution = {"Excellent": 0, "Good": 0, "Needs Improvement": 0}
    first_pass_ok = 0

    for d in all_drafts:
        rr = d.rule_results or {}
        score = rr.get("score", 0)
        scores.append(score)
        rating = rr.get("quality_rating", "Needs Improvement")
        quality_distribution[rating] = quality_distribution.get(rating, 0) + 1
        if not rr.get("has_errors", True):
            first_pass_ok += 1

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    first_pass_rate = round((first_pass_ok / len(all_drafts)) * 100, 1) if all_drafts else 0.0
    approval_rate = round((approved_count / total_drafts) * 100, 1) if total_drafts else 0.0
    rejection_rate = round((rejected_count / total_drafts) * 100, 1) if total_drafts else 0.0

    # Marketplace coverage
    marketplace_counts = {}
    mp_rows = (
        db.query(ListingDraft.marketplace, func.count(ListingDraft.id))
        .group_by(ListingDraft.marketplace)
        .all()
    )
    for mp, count in mp_rows:
        marketplace_counts[mp] = count

    live_on_amazon = (
        db.query(func.count(ListingDraft.id))
        .filter(ListingDraft.marketplace == "amazon", ListingDraft.status == "live")
        .scalar() or 0
    )

    return {
        "overview": {
            "total_products": total_products,
            "total_drafts": total_drafts,
            "products_with_drafts": products_with_drafts,
            "products_without_drafts": total_products - products_with_drafts,
            "coverage_percent": round((products_with_drafts / total_products) * 100, 1) if total_products else 0.0,
        },
        "pipeline": {
            "status_counts": status_counts,
            "draft": draft_count,
            "approved": approved_count,
            "live": live_count,
        },
        "quality": {
            "avg_score": avg_score,
            "max_possible_score": 25,
            "first_pass_rate": first_pass_rate,
            "approval_rate": approval_rate,
            "rejection_rate": rejection_rate,
            "score_distribution": quality_distribution,
        },
        "marketplace": {
            "drafts_per_marketplace": marketplace_counts,
            "live_on_amazon": live_on_amazon,
        },
    }


@router.get("/draft-stats", summary="Get draft pipeline summary stats")
def get_draft_stats(db: Session = Depends(get_db)):
    """Quick stats for dashboard header cards."""
    total = db.query(func.count(ListingDraft.id)).scalar() or 0

    status_rows = (
        db.query(ListingDraft.status, func.count(ListingDraft.id))
        .group_by(ListingDraft.status)
        .all()
    )
    status_counts = {s: c for s, c in status_rows}

    # Average quality score
    all_drafts = db.query(ListingDraft).all()
    scores = [
        (d.rule_results or {}).get("score", 0)
        for d in all_drafts
    ]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    return {
        "total_drafts": total,
        "status_counts": status_counts,
        "avg_quality_score": avg_score,
        "max_quality_score": 25,
    }
