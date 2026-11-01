"""Nothing outside the database is written as product data: no defaults, placeholders or fake IDs."""
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.models.draft import ListingDraft
from app.models.product import Product
from app.seeds import seed_pilot_data
from app.services.ai_service import AIService
from app.services.amazon_adapter import AmazonAdapter
from app.services.catalogue_parser import CatalogueParser
from app.services.catalogue_service import CatalogueService

client = TestClient(app)


def _db():
    gen = app.dependency_overrides[get_db]()  # the test database set up in conftest
    return gen, next(gen)


def test_import_matches_headers_exactly_and_keeps_meesho_columns_as_attributes():
    csv = (
        "SKU,Product Name,Category,Price,Manufacturer Name,Manufacturer Pincode,Product Description,Group ID\n"
        "IMP-EXACT-1,Cotton runner,Home Decor,499,Rangrez Textiles,641604,Long runner,Group 01\n"
    ).encode()
    products, errors, _ = CatalogueParser.parse_file("x.csv", csv)
    assert not errors
    p = products[0]
    # Prefix matching used to send these to brand, name and category
    assert p["brand"] is None and p["name"] == "Cotton runner" and p["category"] == "Home Decor"
    assert p["attributes"]["Manufacturer Name"] == "Rangrez Textiles"
    assert p["attributes"]["Manufacturer Pincode"] == "641604"
    assert p["attributes"]["Group Id"] == "Group 01"


def test_import_invents_no_mrp_and_blank_cells_keep_stored_values():
    gen, db = _db()
    try:
        CatalogueService.batch_upsert_products(db, [{
            "sku": "IMP-KEEP-1", "name": "Keep me", "category": "Planters", "brand": "Rangrez",
            "price": 750.0, "mrp": 999.0, "stock": 12, "attributes": {"Material": "Ceramic"},
        }])
        # A fill-in style file: only SKU, name and one new attribute
        products, errors, _ = CatalogueParser.parse_file(
            "fill.csv", b"SKU,Product Name,HSN ID\nIMP-KEEP-1,Keep me,69120040\n")
        assert not errors and products[0]["mrp"] is None and products[0]["price"] is None
        CatalogueService.batch_upsert_products(db, products)
        stored = CatalogueService.get_by_sku(db, "IMP-KEEP-1")
        db.refresh(stored)
        assert (stored.price, stored.mrp, stored.stock) == (750.0, 999.0, 12)
        assert (stored.category, stored.brand) == ("Planters", "Rangrez")
        assert stored.attributes == {"Material": "Ceramic", "Hsn Id": "69120040"}
    finally:
        gen.close()


def test_import_ignores_an_image_count_instead_of_inventing_filenames():
    products, _, warnings = CatalogueParser.parse_file("x.csv", b"SKU,Product Name,Price,Images\nIMP-IMG-1,Bell,99,3\n")
    assert products[0]["images"] == []
    assert any(w.field == "images" for w in warnings)


def test_seed_only_adds_missing_skus_and_never_overwrites():
    gen, db = _db()
    try:
        product = CatalogueService.get_by_sku(db, "JBP-101")
        original_price = product.price
        product.price = 1111.0
        db.commit()
        count_before = db.query(Product).count()
        seed_pilot_data.seed_database()
        db.refresh(product)
        assert product.price == 1111.0  # stored data wins over the seed file
        assert db.query(Product).count() == count_before  # every seed SKU exists, so nothing is added
        product.price = original_price
        db.commit()
    finally:
        gen.close()


def test_meesho_publish_is_refused_without_changing_the_draft():
    gen, db = _db()
    try:
        product = CatalogueService.get_by_sku(db, "JBP-102")
        draft = ListingDraft(product_id=product.id, marketplace="meesho", title="Meesho publish test",
                             bullets=[], description="", keywords=[], status="approved", is_approved=True)
        db.add(draft)
        db.commit()
        res = client.post(f"/api/v1/drafts/{draft.id}/publish")
        assert res.status_code == 409 and "supplier.meesho.com" in res.json()["detail"]
        db.refresh(draft)
        assert draft.status == "approved" and draft.external_listing_id is None
    finally:
        gen.close()


def test_ai_post_processing_adds_only_the_products_own_attributes():
    product = Product(sku="X1", name="Cotton bedsheet", category="Bedsheets", brand="B", price=100,
                      attributes={"Material": "Cotton"}, images=[])
    out = AIService._enrich_with_apple_grade_specs_and_aplus(product, "B", {"title": "t", "technical_specs": {}})
    assert set(out["technical_specs"].values()) == {"Cotton"}  # no sample sizes, weights or "India"
    assert out["aplus_content"] == {}  # no default headline, story, cards or comparison claims


def test_amazon_legal_metrology_comes_only_from_attributes():
    draft = {"title": "t", "bullets": [], "description": "", "keywords": []}
    bare = AmazonAdapter.build_sp_api_listing_payload(draft, {"sku": "A1", "name": "Bell", "category": "Pooja items",
                                                               "price": 500, "attributes": {}})["attributes"]
    for invented in ("country_of_origin", "manufacturer", "packer", "importer", "net_quantity", "maximum_retail_price"):
        assert invented not in bare

    full = AmazonAdapter.build_sp_api_listing_payload(draft, {
        "sku": "A2", "name": "Bell", "category": "Pooja items", "price": 500, "mrp": 799,
        "attributes": {"Country of Origin": "India", "Manufacturer Name": "Rangrez", "Manufacturer Address": "Tiruppur"},
    })["attributes"]
    assert full["country_of_origin"][0]["value"] == "IN"
    assert full["manufacturer"][0]["value"] == "Rangrez, Tiruppur"
    assert full["maximum_retail_price"][0]["value_with_tax"] == 799.0


def test_amazon_legal_metrology_ignores_values_the_draft_specs_added():
    # AI-written technical specs are copy, not compliance data
    draft = {"title": "t", "bullets": [], "description": "", "keywords": [],
             "technical_specs": {"Country of Origin": "India", "Manufacturer": "Made-up Pvt Ltd",
                                 "Net Quantity": "1", "Material": "Cotton"}}
    attrs = AmazonAdapter.build_sp_api_listing_payload(draft, {"sku": "A3", "name": "Bell", "category": "Pooja items",
                                                                "price": 500, "attributes": {}})["attributes"]
    for invented in ("country_of_origin", "manufacturer", "net_quantity"):
        assert invented not in attrs
    assert attrs["material"][0]["value"] == "Cotton"  # ordinary specs still pass through
