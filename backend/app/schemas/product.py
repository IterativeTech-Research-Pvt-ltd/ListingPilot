from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List, Union
from datetime import datetime

class ProductBase(BaseModel):
    sku: str = Field(..., description="Unique product SKU/identifier")
    name: str = Field(..., description="Product title / name in master catalogue")
    category: str = Field(..., description="Product category (e.g. Bedsheets, Kurtas, Pooja items)")
    brand: str = Field(default="Gulmohar Home", description="Brand name")
    mrp: Optional[float] = Field(default=None, description="Maximum Retail Price in INR")
    price: float = Field(..., description="Selling Price in INR")
    stock: int = Field(default=0, description="Available stock quantity")
    images: List[str] = Field(default_factory=list, description="List of image URLs or paths")
    image_count: Optional[int] = Field(default=None, description="Count of images")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Category-specific specs (Material, Size, Care, etc.)")
    description: Optional[str] = Field(default=None, description="Product notes or master description")
    current_listing: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Current legacy portal listing content")

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    mrp: Optional[float] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    images: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    current_listing: Optional[Dict[str, Any]] = None

class ProductResponse(ProductBase):
    id: int
    image_count: int
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None

    model_config = ConfigDict(from_attributes=True)

class ProductListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProductResponse]
    categories: List[str]

class CatalogueStatsResponse(BaseModel):
    total_skus: int
    total_stock: int
    category_counts: Dict[str, int]
    avg_price: float
    missing_attributes_count: int
    low_photo_count: int
