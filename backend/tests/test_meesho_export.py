"""Meesho export: values come only from product data, gaps block the export."""
import asyncio
import io
import zipfile
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.product import Product
from app.services.ai_service import AIService
from app.services.meesho_adapter import MEESHO_HEADERS, MeeshoAdapter, MeeshoExportIncomplete
from app.services.rule_engine import RuleEngine
from app.core.database import get_db

client = TestClient(app)

LEGAL = {
    "Country of Origin": "India",
    "Manufacturer Name": "Rangrez Textiles",
    "Manufacturer Address": "12 Udyog Vihar, Tiruppur, Tamil Nadu",
    "Manufacturer Pincode": "641604",
    "Packer Name": "Rangrez Textiles",
    "Packer Address": "12 Udyog Vihar, Tiruppur, Tamil Nadu",
    "Packer Pincode": "641604",
    "Importer Name": "Rangrez Textiles",
    "Importer Address": "12 Udyog Vihar, Tiruppur, Tamil Nadu",
    "Importer Pincode": "641604",
}


def tshirt(sku, title, **attr_overrides):
    attrs = {
        **LEGAL,
        "Size": "M",
        "GST %": "5",
        "HSN ID": "61091000",
        "Net Weight (gms)": "180",
        "Color": "Black",
        "Material": "100% cotton",
        "Fit/Shape": "Regular",
        "Neck": "Round",
        "Net Quantity (N)": "1",
        "Occasion": "Casual",
        "Pattern": "Solid",
        "Print Or Pattern Type": "Solid",
        "Sleeve Length": "Short Sleeves",
        "Chest Size": "40",
        "Length Size": "27",
        "Shoulder Size": "17",
    }
    attrs.update(attr_overrides)
    attrs = {k: v for k, v in attrs.items() if v is not None}
    return {
        "sku": sku, "name": title, "category": "Tshirts", "brand": "Gulmohar Home",
        "price": 499.0, "mrp": 799.0, "stock": 12,
        "attributes": attrs,
        "images": ["https://example.com/front.jpg"],
        "draft": {"title": title, "bullets": ["SOFT COTTON — breathable"], "description": "Plain black tee."},
    }


def sheet_row(buf, row=5):
    tmpl = MeeshoAdapter.find_template("Tshirts")
    ws = openpyxl.load_workbook(buf)[tmpl["sheet_name"]]
    return {name: ws.cell(row=row, column=col).value for col, name in tmpl["columns"].items()}


def export_problems(items, category="Tshirts"):
    with pytest.raises(MeeshoExportIncomplete) as exc:
        MeeshoAdapter.generate_batch_export(items, category_filter=category)
    return exc.value.problems


def test_complete_product_exports_its_own_values():
    buf, _, _ = MeeshoAdapter.generate_batch_export([tshirt("TS-1", "Gulmohar Home Black Cotton Tee")], category_filter="Tshirts")
    row = sheet_row(buf)
    assert row["Product Name"] == "Gulmohar Home Black Cotton Tee"
    assert row["Meesho Price"] == 499.0  # the seller's price, not a computed discount
    assert row["MRP"] == 799.0
    assert row["HSN ID"] == "61091000"
    assert row["Fabric"] == "Cotton"  # "100% cotton" names exactly one option
    assert row["Manufacturer Name"] == "Rangrez Textiles"
    assert row["Net Weight (gms)"] == 180
    assert row["Wrong/Defective Return Discount(₹)"] is None  # optional and not in the data
    assert row["Brand Name"] == "Gulmohar Home"
    assert row["Brand"] is None  # brand dropdown is never auto-picked


def test_missing_compulsory_fields_block_export_instead_of_defaults():
    problems = export_problems([tshirt("TS-2", "Tee two", **{"HSN ID": None, "Manufacturer Name": None, "Net Weight (gms)": None})])
    fields = {p["field"] for p in problems if p["blocking"]}
    assert {"HSN ID", "Manufacturer Name", "Net Weight (gms)"} <= fields


def test_values_outside_the_dropdown_are_not_snapped():
    # Old behaviour: HSN 6109 fell through to the first option and unknown sizes became a default
    problems = export_problems([tshirt("TS-3", "Tee three", **{"HSN ID": "6109", "Size": "Universal"})])
    by_field = {p["field"]: p for p in problems}
    assert by_field["HSN ID"]["blocking"] and "'6109'" in by_field["HSN ID"]["reason"]
    assert by_field["Variation"]["blocking"]


def test_shared_product_name_across_designs_blocks_export():
    items = [tshirt("TS-4", "Same tee title"), tshirt("TS-5", "Same tee title", Color="White")]
    problems = export_problems(items)
    assert {p["sku"] for p in problems if p["field"] == "Product Name"} == {"TS-4", "TS-5"}


def test_size_variants_of_one_style_may_share_a_name():
    items = [tshirt("TS-6M", "Variant tee", **{"Style ID": "TS-6"}),
             tshirt("TS-6L", "Variant tee", **{"Style ID": "TS-6", "Size": "L"})]
    buf, _, _ = MeeshoAdapter.generate_batch_export(items, category_filter="Tshirts")
    assert sheet_row(buf, 5)["Variation"] == "M" and sheet_row(buf, 6)["Variation"] == "L"


@pytest.mark.parametrize("val, options, col, expected", [
    ("180 TC", ["100", "180", "200"], "Thread Count", "180"),
    ("5.0", ["18", "5"], "GST %", "5"),
    ("100% cotton", ["Cotton", "Cotton Blend", "Polyester"], "Fabric", "Cotton"),
    ("Cotton blend fabric", ["Cotton", "Cotton Blend"], "Fabric", "Cotton Blend"),
    ("90 x 100 in (double)", ["Double", "King", "Single"], "Variation", "Double"),
    ("Double / King, 90 x 108 in", ["Double", "King"], "Variation", None),  # ambiguous
    ("Floral, hand block print", ["Batik", "Floral", "Geometric"], "Print or Pattern Type", "Floral"),
    ("Indigo and white", ["Blue", "White"], "Color", None),  # colour must match exactly
    ("6109", ["392410", "6304"], "HSN ID", None),
    ("Gulmohar", ["Gulmohar Home Decor"], "Brand", None),
    ("group  1", ["Group  1", "Group  10"], "Group ID", "Group  1"),  # template spelling kept
])
def test_dropdown_matching_is_high_confidence_only(val, options, col, expected):
    assert MeeshoAdapter._match_dropdown_option(val, options, col_name=col) == expected


def test_template_less_category_blocks_on_missing_compulsory_fields():
    item = tshirt("PL-1", "Ceramic planter", **{k: None for k in ["HSN ID", "Manufacturer Name"]})
    item["category"] = "Planters"
    problems = export_problems([item], category="Planters")
    assert {"HSN Code", "Manufacturer Name"} <= {p["field"] for p in problems}


def test_zip_export_of_complete_products():
    planter = tshirt("PL-2", "Blue pottery planter", **{"Manufacturer Address": "Jaipur", "Care": "Wipe clean"})
    planter["category"] = "Planters"
    buf, media_type, _ = MeeshoAdapter.generate_batch_export(
        [tshirt("TS-7", "Zip tee"), planter], force_zip=True)
    assert media_type == "application/zip"
    names = zipfile.ZipFile(buf).namelist()
    assert sorted(names) == ["ListingPilot_Meesho_Planters.xlsx", "ListingPilot_Meesho_Tshirts.xlsx"]
    ws = openpyxl.load_workbook(io.BytesIO(zipfile.ZipFile(buf).read(names[0])))["Validate Sheet"]
    assert [c.value for c in ws[1]] == MEESHO_HEADERS


def test_export_endpoint_reports_problems_with_422():
    res = client.get("/api/v1/drafts/meesho/export?category=Bedsheets")
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert "blocked" in detail["message"]
    assert any(p["sku"] == "JBP-101" for p in detail["problems"])


def test_export_endpoint_streams_complete_category():
    item = tshirt("TS-API-1", "Endpoint tee")
    db_gen = app.dependency_overrides[get_db]()  # the test database set up in conftest
    db = next(db_gen)
    try:
        if not db.query(Product).filter(Product.sku == "TS-API-1").first():
            db.add(Product(**{k: item[k] for k in ["sku", "name", "category", "brand", "price", "mrp", "stock", "attributes", "images"]}))
            db.commit()
    finally:
        db_gen.close()
    res = client.get("/api/v1/drafts/meesho/export?category=Tshirts")
    assert res.status_code == 200, res.text
    assert sheet_row(io.BytesIO(res.content))["SKU ID"] == "TS-API-1"


def test_rule_engine_warns_on_words_meesho_flags():
    product = Product(sku="X", name="x", category="Bedsheets", price=100, attributes={}, images=["a"], image_count=1)
    draft = {"title": "A cotton bedsheet set", "bullets": ["CARE — machine wash"], "description": "Soft comfort."}
    issues = RuleEngine.evaluate(product, draft, marketplace="meesho")["issues"]
    flagged = [i for i in issues if i["kind"] == "meesho_flagged_word"]
    assert flagged and flagged[0]["level"] == "warning"
    assert not [i for i in RuleEngine.evaluate(product, draft, marketplace="amazon")["issues"] if i["kind"] == "meesho_flagged_word"]


def test_meesho_prompt_and_template_copy_avoid_flagged_words(monkeypatch):
    product = Product(sku="JBP-1", name="Bedsheet", category="Bedsheets", brand="Gulmohar Home", price=1299,
                      attributes={"Colour": "Blue", "Care": "Machine wash cold"}, images=[])
    monkeypatch.setattr(settings, "AI_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test_key")
    fake = AsyncMock(return_value={"title": "t"})
    with patch.object(AIService, "_call_chat_completions", fake):
        asyncio.run(AIService.generate_listing(product, marketplace="meesho"))
        asyncio.run(AIService.generate_listing(product, marketplace="amazon"))
    meesho_prompt, amazon_prompt = fake.call_args_list[0].args[5], fake.call_args_list[1].args[5]
    assert "Meesho rules" in meesho_prompt and "WASH & MAINTENANCE" in meesho_prompt
    assert "Meesho rules" not in amazon_prompt

    bullets = AIService._fallback_generator(product, "Gulmohar Home", marketplace="meesho")["bullets"]
    assert not any(b.upper().startswith("CARE") for b in bullets)
