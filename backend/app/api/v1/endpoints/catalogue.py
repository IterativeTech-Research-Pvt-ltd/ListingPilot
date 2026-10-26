from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import io
import urllib.parse

from app.core.database import get_db
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    CatalogueStatsResponse
)
from app.schemas.import_export import ImportSummaryResponse
from app.services.catalogue_service import CatalogueService
from app.services.template_generator import generate_master_catalogue_template
from app.services.catalogue_parser import CatalogueParser
from app.services.catalogue_exporter import CatalogueExporter

router = APIRouter()

@router.get("/categories", response_model=List[str], summary="Get all distinct product categories (CAT-4)")
def get_categories(db: Session = Depends(get_db)):
    """Returns a list of all distinct product categories in the Master Catalogue."""
    return CatalogueService.get_categories(db)

import uuid
import shutil
from pathlib import Path

UPLOAD_DIR = Path(__file__).resolve().parents[4] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload-image", summary="Upload product image file (File or Link workflow)")
async def upload_product_image(file: UploadFile = File(...)):
    """Accepts image files (.jpg, .jpeg, .png, .webp), saves to backend/uploads, and returns accessible URL."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        raise HTTPException(status_code=400, detail="Unsupported image format. Allowed: .jpg, .jpeg, .png, .webp")
    
    unique_filename = f"prod_{uuid.uuid4().hex[:12]}{ext}"
    target_path = UPLOAD_DIR / unique_filename
    
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    image_url = f"http://localhost:8000/static/uploads/{unique_filename}"
    return {
        "success": True,
        "url": image_url,
        "filename": unique_filename,
        "original_name": file.filename
    }

@router.get("/template", summary="Download official Master Catalogue Excel Template (CAT-1)")
def download_template():
    """Generates and streams the official Master Catalogue Excel template (.xlsx) with instructions & sample data."""
    buffer = generate_master_catalogue_template()
    filename = "ListingPilot_Master_Catalogue_Template.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.post("/import", response_model=ImportSummaryResponse, summary="Import Master Catalogue from Excel, CSV, or Tally export (CAT-2)")
async def import_catalogue(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Parses and imports products from:
    - Master Catalogue Excel (.xlsx)
    - Legacy / Generic CSV
    - Tally XML / Excel exports
    Validates mandatory fields, checks for duplicates, and upserts valid records.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        products, errors, warnings = CatalogueParser.parse_file(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

    created_count, updated_count = 0, 0
    if products:
        created_count, updated_count = CatalogueService.batch_upsert_products(db, products)

    categories_detected = list(set(p.get("category", "") for p in products if p.get("category")))

    total_rows = len(products) + len([e for e in errors if e.severity == "error"])
    success = len(errors) == 0

    return ImportSummaryResponse(
        success=success,
        filename=file.filename,
        total_rows=total_rows,
        imported_count=created_count,
        updated_count=updated_count,
        failed_count=len(errors),
        warnings_count=len(warnings),
        errors=errors,
        warnings=warnings,
        categories_detected=categories_detected,
        message=f"Successfully imported {created_count} new and updated {updated_count} existing products."
        if not errors
        else f"Imported with {len(errors)} issues to review."
    )

@router.get("/export", summary="Export Full Master Catalogue in Excel, CSV, or JSON (CAT-3)")
def export_catalogue(
    format: str = Query("xlsx", pattern="^(xlsx|csv|json)$"),
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Exports the complete master catalogue at any time, ensuring total client data portability (CAT-3).
    Supports Excel (.xlsx), CSV, and raw JSON.
    """
    products, _ = CatalogueService.get_products(db, category=category, search=search, page=1, page_size=100000)

    if format == "xlsx":
        buf = CatalogueExporter.export_excel(products)
        filename = "ListingPilot_Master_Catalogue.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    elif format == "csv":
        buf = CatalogueExporter.export_csv(products)
        filename = "ListingPilot_Master_Catalogue.csv"
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    elif format == "json":
        json_str = CatalogueExporter.export_json(products)
        filename = "ListingPilot_Master_Catalogue.json"
        return Response(
            content=json_str,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

@router.get("/products", response_model=ProductListResponse, summary="List master catalogue products")
def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by SKU, name, brand"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    products, total = CatalogueService.get_products(
        db, category=category, search=search, page=page, page_size=page_size
    )
    categories = CatalogueService.get_categories(db)
    
    return ProductListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ProductResponse.model_validate(p) for p in products],
        categories=categories
    )

@router.get("/products/{product_id}", response_model=ProductResponse, summary="Get product details")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = CatalogueService.get_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse.model_validate(product)

@router.post("/products", response_model=ProductResponse, status_code=201, summary="Create a new product")
def create_product(product_in: ProductCreate, db: Session = Depends(get_db)):
    try:
        product = CatalogueService.create_product(db, product_in)
        return ProductResponse.model_validate(product)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/products/{product_id}", response_model=ProductResponse, summary="Update product")
def update_product(product_id: int, product_update: ProductUpdate, db: Session = Depends(get_db)):
    product = CatalogueService.update_product(db, product_id, product_update)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse.model_validate(product)

@router.delete("/products/{product_id}", summary="Delete product")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    success = CatalogueService.delete_product(db, product_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True, "message": "Product deleted successfully"}

@router.get("/stats", response_model=CatalogueStatsResponse, summary="Get catalogue health & statistics")
def get_stats(db: Session = Depends(get_db)):
    return CatalogueService.get_stats(db)

@router.get("/categories", response_model=List[str], summary="Get list of categories")
def get_categories(db: Session = Depends(get_db)):
    return CatalogueService.get_categories(db)
