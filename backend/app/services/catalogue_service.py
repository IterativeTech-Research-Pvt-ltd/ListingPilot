from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional, Tuple, Dict, Any
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.template_generator import CATEGORIES_INFO

class CatalogueService:
    @staticmethod
    def get_products(
        db: Session,
        category: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Product], int]:
        query = db.query(Product)
        if category and category != "All":
            query = query.filter(Product.category == category)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Product.sku.ilike(search_term),
                    Product.name.ilike(search_term),
                    Product.brand.ilike(search_term),
                    Product.category.ilike(search_term)
                )
            )
        total = query.count()
        offset = (page - 1) * page_size
        products = query.order_by(Product.id.asc()).offset(offset).limit(page_size).all()
        return products, total

    @staticmethod
    def get_by_sku(db: Session, sku: str) -> Optional[Product]:
        return db.query(Product).filter(Product.sku == sku).first()

    @staticmethod
    def get_by_id(db: Session, product_id: int) -> Optional[Product]:
        return db.query(Product).filter(Product.id == product_id).first()

    @staticmethod
    def create_product(db: Session, product_in: ProductCreate) -> Product:
        existing = CatalogueService.get_by_sku(db, product_in.sku)
        if existing:
            raise ValueError(f"Product with SKU '{product_in.sku}' already exists.")
        
        img_count = product_in.image_count or (len(product_in.images) if product_in.images else 0)
        product = Product(
            sku=product_in.sku,
            name=product_in.name,
            category=product_in.category,
            brand=product_in.brand,
            mrp=product_in.mrp or (product_in.price * 1.25 if product_in.price else None),
            price=product_in.price,
            stock=product_in.stock,
            images=product_in.images,
            image_count=img_count,
            attributes=product_in.attributes,
            description=product_in.description,
            current_listing=product_in.current_listing
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def update_product(db: Session, product_id: int, product_update: ProductUpdate) -> Optional[Product]:
        product = CatalogueService.get_by_id(db, product_id)
        if not product:
            return None

        update_data = product_update.model_dump(exclude_unset=True)
        if "images" in update_data and update_data["images"] is not None:
            update_data["image_count"] = len(update_data["images"])

        for field, value in update_data.items():
            setattr(product, field, value)

        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def delete_product(db: Session, product_id: int) -> bool:
        product = CatalogueService.get_by_id(db, product_id)
        if not product:
            return False
        db.delete(product)
        db.commit()
        return True

    @staticmethod
    def batch_upsert_products(db: Session, raw_products: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Upserts imported products into the database.
        Returns (created_count, updated_count).
        """
        created_count = 0
        updated_count = 0

        for item in raw_products:
            sku = item.get("sku")
            if not sku:
                continue

            existing = CatalogueService.get_by_sku(db, sku)
            img_list = item.get("images", [])
            img_count = item.get("image_count", len(img_list))

            if existing:
                existing.name = item.get("name", existing.name)
                existing.category = item.get("category", existing.category)
                existing.brand = item.get("brand", existing.brand)
                if item.get("mrp") is not None:
                    existing.mrp = item.get("mrp")
                if item.get("price") is not None:
                    existing.price = item.get("price")
                if item.get("stock") is not None:
                    existing.stock = item.get("stock")
                if img_list:
                    existing.images = img_list
                    existing.image_count = img_count
                if item.get("attributes"):
                    # Merge attributes
                    merged_attrs = dict(existing.attributes or {})
                    merged_attrs.update(item["attributes"])
                    existing.attributes = merged_attrs
                if item.get("description"):
                    existing.description = item["description"]
                if item.get("current_listing"):
                    existing.current_listing = item["current_listing"]
                updated_count += 1
            else:
                new_prod = Product(
                    sku=sku,
                    name=item.get("name", ""),
                    category=item.get("category", "General"),
                    brand=item.get("brand", "Gulmohar Home"),
                    mrp=item.get("mrp"),
                    price=item.get("price", 0.0),
                    stock=item.get("stock", 0),
                    images=img_list,
                    image_count=img_count,
                    attributes=item.get("attributes", {}),
                    description=item.get("description", ""),
                    current_listing=item.get("current_listing", {})
                )
                db.add(new_prod)
                created_count += 1

        db.commit()
        return created_count, updated_count

    @staticmethod
    def get_categories(db: Session) -> List[str]:
        results = db.query(Product.category).distinct().order_by(Product.category).all()
        categories = [r[0] for r in results if r[0]]
        # Include default categories from CATEGORIES_INFO if empty
        if not categories:
            categories = [c["category"] for c in CATEGORIES_INFO]
        return categories

    @staticmethod
    def get_stats(db: Session) -> Dict[str, Any]:
        all_products = db.query(Product).all()
        total_skus = len(all_products)
        total_stock = sum(p.stock for p in all_products)
        avg_price = (sum(p.price for p in all_products) / total_skus) if total_skus > 0 else 0.0

        cat_counts = {}
        missing_attrs_count = 0
        low_photo_count = 0

        # Mapping of required attributes by category
        req_map = {c["category"].lower(): c["required_attrs"] for c in CATEGORIES_INFO}

        for p in all_products:
            cat = p.category or "Other"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            
            # Check low photos (< 3)
            p_img_count = p.image_count or (len(p.images) if p.images else 0)
            if p_img_count < 3:
                low_photo_count += 1

            # Check missing required attributes
            req_attrs = req_map.get(cat.lower(), [])
            if req_attrs:
                p_attrs = p.attributes or {}
                if any(not str(p_attrs.get(ra, "")).strip() for ra in req_attrs):
                    missing_attrs_count += 1

        return {
            "total_skus": total_skus,
            "total_stock": total_stock,
            "category_counts": cat_counts,
            "avg_price": round(avg_price, 2),
            "missing_attributes_count": missing_attrs_count,
            "low_photo_count": low_photo_count
        }
