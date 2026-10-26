from sqlalchemy import Column, Integer, String, Float, Text, JSON, DateTime
from datetime import datetime, timezone
from app.core.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(100), index=True, nullable=False)
    brand = Column(String(100), default="Gulmohar Home", nullable=False)
    mrp = Column(Float, nullable=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    
    # List of image URLs or relative image file paths
    images = Column(JSON, default=list)
    image_count = Column(Integer, default=0)
    
    # Category attributes dict (e.g. {"Material": "100% cotton", "Size": "90 x 100 in", "Care": "Machine wash"})
    attributes = Column(JSON, default=dict)
    
    # Optional raw notes or original description from import
    description = Column(Text, nullable=True)
    
    # Current existing portal listing info (used for baseline comparison & gap analysis)
    # e.g. {"title": "...", "bullets": [...], "filled": 2, "flags": [...]}
    current_listing = Column(JSON, default=dict)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "category": self.category,
            "brand": self.brand,
            "mrp": self.mrp,
            "price": self.price,
            "stock": self.stock,
            "images": self.images or [],
            "image_count": self.image_count or (len(self.images) if self.images else 0),
            "attributes": self.attributes or {},
            "description": self.description or "",
            "current_listing": self.current_listing or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
