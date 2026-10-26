from sqlalchemy import Column, Integer, String, Float, Text, JSON, DateTime, ForeignKey, Boolean
from datetime import datetime, timezone
from app.core.database import Base

class ListingDraft(Base):
    __tablename__ = "listing_drafts"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False)
    marketplace = Column(String(50), default="amazon", nullable=False) # amazon, flipkart, meesho
    
    # Generated content (GEN-1 - GEN-4)
    title = Column(String(500), nullable=False)
    bullets = Column(JSON, default=list) # List of 5 strings
    description = Column(Text, nullable=True)
    keywords = Column(JSON, default=list) # List of search keywords
    
    # Workflow status: draft, approved, live
    status = Column(String(50), default="draft", nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)
    
    # Rule checks result (RUL-1 - RUL-5)
    # e.g. {"passed": bool, "score": int, "issues": [{"lvl": "bad"|"warn", "text": "..."}]}
    rule_results = Column(JSON, default=dict)
    
    # Exhaustive specifications & A+ Enhanced Brand Content (Apple-grade)
    technical_specs = Column(JSON, default=dict)
    aplus_content = Column(JSON, default=dict)

    # Marketplace publication metadata (AMZ-1, ERR-1)
    marketplace_sku = Column(String(100), nullable=True)
    external_listing_id = Column(String(100), nullable=True) # ASIN for Amazon, FSN for Flipkart
    last_sync_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "marketplace": self.marketplace,
            "title": self.title,
            "bullets": self.bullets or [],
            "description": self.description or "",
            "keywords": self.keywords or [],
            "technical_specs": self.technical_specs or {},
            "aplus_content": self.aplus_content or {},
            "status": self.status,
            "is_approved": self.is_approved,
            "rule_results": self.rule_results or {},
            "marketplace_sku": self.marketplace_sku,
            "external_listing_id": self.external_listing_id,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
