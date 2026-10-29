import os
import tempfile
from urllib.parse import urlparse

# Keep tests away from real data; must be set before app imports.
# The settings store lives in a throwaway directory per run; the database is a separate Neon branch.
_TEST_DIR = tempfile.mkdtemp(prefix="listingpilot-tests-")
os.environ["LISTINGPILOT_SETTINGS_FILE"] = os.path.join(_TEST_DIR, "dynamic_settings.json")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core import database
from app.core.database import Base, get_db
from app.main import app
from app.models.product import Product
from app.models.draft import ListingDraft


def _test_database_url() -> str:
    url = (settings.TEST_DATABASE_URL or "").strip()
    if not url.startswith(("postgresql://", "postgres://")):
        raise pytest.UsageError(
            "TEST_DATABASE_URL must point at a separate Neon branch (postgresql://...); see .env.example."
        )
    test, main = urlparse(url), urlparse(settings.DATABASE_URL or "")
    if (test.hostname, test.path) == (main.hostname, main.path):
        raise pytest.UsageError(
            "TEST_DATABASE_URL is the app's DATABASE_URL. Tests drop and recreate tables; use a separate Neon branch."
        )
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg2://", 1)


test_engine = create_engine(
    _test_database_url(), connect_args={"connect_timeout": database.NEON_CONNECT_TIMEOUT_S}, pool_pre_ping=True
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
# Code that opens sessions directly (Celery tasks) must hit the test branch too, never the app database
database.SessionLocal.configure(bind=test_engine)
database.engine = test_engine

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# No test may call a real AI provider: without keys generation uses the built-in generator.
# Tests of a provider set their own fake key and mock httpx (see test_ai_groq.py).
for _key in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
    setattr(settings, _key, "")

from app.seeds.seed_pilot_data import PILOT_PRODUCTS
from app.services.catalogue_service import CatalogueService

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    try:
        database.check_connection(test_engine)
    except RuntimeError as e:
        pytest.exit(f"Neon test branch: {e}", returncode=3)
    # Fresh tables every run so leftovers from earlier runs can't leak into results
    Base.metadata.drop_all(bind=test_engine)
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

