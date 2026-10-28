import os
import tempfile

# Keep tests away from the real settings/credentials store; must be set before app imports
os.environ["LISTINGPILOT_SETTINGS_FILE"] = os.path.join(
    tempfile.mkdtemp(prefix="listingpilot-tests-"), "dynamic_settings.json"
)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, get_db
from app.main import app
from app.models.product import Product
from app.models.draft import ListingDraft

TEST_DATABASE_URL = "sqlite:///./test_pilot.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

from app.seeds.seed_pilot_data import PILOT_PRODUCTS
from app.services.catalogue_service import CatalogueService

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    
    existing_count = db.query(Product).count()
    if existing_count < 50:
        CatalogueService.batch_upsert_products(db, PILOT_PRODUCTS)
        # Add additional items to reach 55
        extra_products = []
        categories = ["Bedsheets", "Pooja items", "Kurtas", "Planters", "Ethnic footwear", "Quilts"]
        for i in range(1, 41):
            cat = categories[i % len(categories)]
            extra_products.append({
                "sku": f"PILOT-{cat[:3].upper()}-{100 + i}",
                "name": f"Handmade {cat.lower()} variant {i} - artisan collection",
                "category": cat,
                "brand": "Gulmohar Home",
                "mrp": 1000 + (i * 50),
                "price": 750 + (i * 40),
                "stock": 10 + (i * 3),
                "images": [
                    "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af",
                    "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2",
                    "https://images.unsplash.com/photo-1605371924599-2d0365da1ae0"
                ],
                "attributes": {
                    "Material": "Artisan handmade material",
                    "Dimensions": "Standard Indian dimensions",
                    "Care": "Clean with dry cloth"
                },
                "description": f"Traditional handcrafted {cat.lower()} with authentic detailing."
            })
        CatalogueService.batch_upsert_products(db, extra_products)
    
    db.close()
    yield
