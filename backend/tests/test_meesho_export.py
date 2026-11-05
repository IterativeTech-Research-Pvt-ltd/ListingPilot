"""Meesho export: values come only from product data, gaps block the export."""
import asyncio
import io
import re
import zipfile
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.product import Product
from app.models.draft import ListingDraft
from app.services.ai_service import AIService
from app.services.catalogue_parser import CatalogueParser
from app.services.meesho_adapter import MeeshoAdapter, MeeshoExportIncomplete
from app.services.rule_engine import RuleEngine
from app.core.database import get_db

client = TestClient(app)

# Several official templates share these names (Men's, Women's, Kids'), so test products name theirs
TSHIRTS = "Men Fashion/Mens Clothing/Men Top Wear/Tshirts"
BEDSHEETS = "Home & Kitchen/Home Furnishings/Bedding & Linen/Bedsheets"
SNEAKERS = "Men Fashion/Footwear/Shoes/Sneakers"

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
        "Meesho Category": TSHIRTS,
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
        "draft": {"title": title, "bullets": ["SOFT COTTON — breathable"], "description": "Plain black tee.", "is_approved": True},
    }


def sheet_row(buf, row=5):
    tmpl = MeeshoAdapter.find_template(TSHIRTS)
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


def bedsheet(sku, title, **attr_overrides):
    attrs = {
        **LEGAL,
        "Meesho Category": BEDSHEETS,
        "Material": "100% cotton",
        "Size": "90 x 100 in (double)",
        "Thread count": "180 TC",
        "Colour": "Indigo and white",
        "Color": "Blue",
        "Pattern": "Floral, hand block print",
        "Included": "1 bedsheet + 2 pillow covers (17 x 27 in)",
        "GST %": "5",
        "HSN ID": "63041910",
        "Net Weight (gms)": "650",
        "Net Quantity (N)": "1",
        # Facts the seller states for Meesho; none can be read off the measurements above
        "Meesho Size": "Double Queen",
        "Care Instructions": "Machine Wash Only",
        "Ideal For": "Adult",
        "Ideal Season": "Summer",
        "Occassion Type": "Others",
        "Quality": "Regular",
        "Type": "Flat Sheets",
    }
    attrs.update(attr_overrides)
    item = tshirt(sku, title)
    item.update(category="Bedsheets", attributes={k: v for k, v in attrs.items() if v is not None})
    return item


def bedsheet_row(buf, row=5):
    tmpl = MeeshoAdapter.find_template(BEDSHEETS)
    ws = openpyxl.load_workbook(buf)[tmpl["sheet_name"]]
    return {name: ws.cell(row=row, column=col).value for col, name in tmpl["columns"].items()}


def test_bedsheet_measurements_come_from_the_stated_sizes():
    buf, _, _ = MeeshoAdapter.generate_batch_export([bedsheet("BS-1", "Indigo floral bedsheet")], category_filter="Bedsheets")
    row = bedsheet_row(buf)
    assert (row["Variation"], row["Thread Count"]) == ("Double", "180")
    assert (row["Product Length"], row["Product Width"], row["Product Dimension Unit"]) == (100, 90, "inch")
    assert row["Dimensions (inches)"] == "90*100-(Double)"  # sides and Variation pick one option
    assert row["No. Of Pillow Covers"] == "2"
    assert row["Size"] == "Double Queen"  # from Meesho Size; Size itself holds the measurement
    assert row["Color"] == "Blue"  # the seller's Meesho colour wins over the descriptive Colour
    assert row["Print or Pattern Type"] == "Floral"


def test_bed_size_is_never_guessed_from_the_measurement():
    # "(double)" could be Double Queen or Double King; the export blocks and names the attribute to set
    problems = export_problems([bedsheet("BS-6", "Unsized bedsheet", **{"Meesho Size": None})], category="Bedsheets")
    by_field = {p["field"]: p for p in problems if p["blocking"]}
    assert set(by_field) == {"Size"} and "add a 'Meesho Size' attribute" in by_field["Size"]["reason"]
    buf = MeeshoAdapter.build_fill_in_sheet([bedsheet("BS-6", "Unsized bedsheet", **{"Meesho Size": None})])
    headers = [c.value for c in openpyxl.load_workbook(buf)["Fill in"][1]]
    assert "Meesho Size" in headers and "Size" not in headers  # importing it can't overwrite the measurement


@pytest.mark.parametrize("size, variation, expected", [
    ("90 x 100 in (double)", "Double", "90*100-(Double)"),
    ("100 x 90 in", "Queen", "100*90-(Queen)"),
    ("90 x 100 in", None, None),  # two options share these sides; no Variation to choose between them
    ("60 x 61 in", "Single", None),  # no option with these sides
    ("Double bed", "Double", None),  # no stated sides
])
def test_dimension_option_needs_the_stated_sides(size, variation, expected):
    from app.services.meesho_adapter import _dimension_option
    options = ["100*90-(Queen)", "90*100-(Double)", "108*108-(King)"]
    assert _dimension_option(size, variation, options) == expected


def test_official_workbook_gets_no_extra_sheets():
    buf, _, _ = MeeshoAdapter.generate_batch_export([bedsheet("BS-2", "Plain bedsheet")], category_filter="Bedsheets")
    master = openpyxl.load_workbook(MeeshoAdapter.find_template(BEDSHEETS)["filepath"])
    assert openpyxl.load_workbook(buf).sheetnames == master.sheetnames


def no_template_item(sku, title):
    """A product in a category no official template matches by name."""
    item = tshirt(sku, title, **{"Meesho Category": None})
    item["category"] = "Pooja items"
    return item


def test_category_without_official_template_is_refused():
    problems = export_problems([no_template_item("PJ-1", "Brass diya")], category="Pooja items")
    assert [(p["sku"], p["field"]) for p in problems] == [("PJ-1", "Template")]
    assert "no Meesho category chosen" in problems[0]["reason"]


def test_a_product_without_a_meesho_category_blocks_the_whole_upload():
    # All or nothing: the ready tee isn't exported alone; the seller fixes the diya or takes it out
    diya = no_template_item("PJ-2", "Brass diya")
    problems = export_problems([tshirt("TS-8", "Kept tee"), diya], category=None)
    assert [(p["sku"], p["category"], p["field"]) for p in problems if p["blocking"]] == [("PJ-2", "Pooja items", "Template")]
    buf, media_type, _ = MeeshoAdapter.generate_batch_export([tshirt("TS-8", "Kept tee")])
    assert media_type.endswith("spreadsheetml.sheet") and sheet_row(buf)["SKU ID"] == "TS-8"
    # The fill-in sheet asks the unplaced item, and only it, for its Meesho Category
    ws = openpyxl.load_workbook(MeeshoAdapter.build_fill_in_sheet([tshirt("TS-8", "Kept tee"), diya]))["Fill in"]
    headers = [c.value for c in ws[1]]
    assert headers[3] == "Meesho Category"
    assert [r[0] for r in ws.iter_rows(min_row=2, values_only=True)] == ["PJ-2"]


def test_meesho_category_from_the_fill_in_sheet_places_the_product():
    diya = no_template_item("PJ-4", "Brass diya")
    wb = openpyxl.load_workbook(MeeshoAdapter.build_fill_in_sheet([diya]))
    assert "Home & Kitchen > Home Decor > Puja Accessories > Puja Articles" in [
        c.value for c in wb["Allowed values"]["A"]]  # the dropdown offers every category's breadcrumb
    ws = wb["Fill in"]
    ws.cell(row=2, column=4, value="Home & Kitchen > Home Decor > Puja Accessories > Puja Articles")
    out = io.BytesIO()
    wb.save(out)
    parsed, errors, _ = CatalogueParser.parse_file("fill.xlsx", out.getvalue())
    assert not errors
    diya["attributes"].update(parsed[0]["attributes"])
    tmpl, _ = MeeshoAdapter.resolve_item_template(diya)
    assert tmpl["breadcrumb"] == "Home & Kitchen > Home Decor > Puja Accessories > Puja Articles"


def test_one_response_lists_every_products_problems():
    diya = no_template_item("PJ-3", "Brass diya")
    problems = export_problems([tshirt("TS-9", "Gappy tee", **{"HSN ID": None}), diya], category=None)
    assert {(p["sku"], p["field"]) for p in problems if p["blocking"]} == {("TS-9", "HSN ID"), ("PJ-3", "Template")}


def test_ethnic_footwear_is_not_sent_to_the_sneakers_template():
    assert MeeshoAdapter.find_template("Ethnic footwear") is None


@pytest.mark.parametrize("category, expected", [
    ("Double Bedsheets", {"Bedsheets"}),
    ("Bed Sheets", {"Bedsheets"}),
    ("T-Shirts", {"Tshirts"}),
    ("Tees", {"Tshirts"}),
    ("Brother & Sister T-Shirts", {"Brother & Sister T-Shirts"}),
    ("Casual Shirts", {"Shirts"}),
    ("Men Fashion/Footwear/Shoes/Sneakers", {"Sneakers"}),
    # Words that merely contain a template's name don't match it
    ("Steel bottles", set()),
    ("Settees", set()),
    ("Sweatshirts", {"Sweatshirts"}),
    ("Shirt Fabric", {"Shirt Fabric"}),
    ("Men", set()),
    ("Pet Bedding", {"Pet Bedding"}),
])
def test_categories_match_templates_by_whole_words(category, expected):
    assert {e["category"] for e in MeeshoAdapter.template_candidates(category)} == expected


def test_a_name_several_templates_fit_is_never_guessed():
    assert len(MeeshoAdapter.template_candidates("Bedsheets")) == 2  # Home & Kitchen and Kids & Toys
    assert MeeshoAdapter.find_template("Bedsheets") is None
    assert MeeshoAdapter.find_template(BEDSHEETS)["path"] == BEDSHEETS
    item = bedsheet("BS-AM-1", "Ambiguous bedsheet", **{"Meesho Category": None})
    problems = export_problems([item], category="Bedsheets")
    assert [p["field"] for p in problems] == ["Template"]
    assert set(problems[0]["candidates"]) == {
        "Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets", "Kids & Toys > Accessories > Unisex > Bedsheets"}


def test_a_name_match_only_suggests_and_never_picks_the_template():
    # 'Planters' fits exactly one template, yet without the seller's choice nothing is exported
    planter = tshirt("PL-S1", "Ceramic planter", **{"Meesho Category": None})
    planter["category"] = "Planters"
    tmpl, suggestions = MeeshoAdapter.resolve_item_template(planter)
    assert tmpl is None and [s["category"] for s in suggestions] == ["Planter"]
    assert "suggested: Home & Kitchen > Gardening > Plant Containers > Planter" in export_problems([planter], category="Planters")[0]["reason"]


def test_suggestions_leave_out_templates_for_another_audience():
    # 'Kurtas' fits one template, under Men Fashion: it isn't suggested for a women's kurta
    women = tshirt("KU-1", "Women's straight kurta", **{"Meesho Category": None})
    men = tshirt("KU-2", "Men's short kurta", **{"Meesho Category": None})
    women["category"] = men["category"] = "Kurtas"
    assert MeeshoAdapter.suggest_templates(women) == []
    assert [s["id"] for s in MeeshoAdapter.suggest_templates(men)] == ["10149"]
    # Chosen explicitly, the seller's choice stands
    women["attributes"]["Meesho Category"] = "Women Fashion > Ethnic Wear > Kurtis, Sets & Fabrics > Kurtis"
    assert MeeshoAdapter.resolve_item_template(women)[0]["category"] == "Kurtis"


def test_template_ids_and_breadcrumbs_keep_meeshos_real_names():
    # 39 names contain '/', which their folders couldn't keep ('Memory / RAM' is saved as 'Memory RAM')
    ram = MeeshoAdapter.template_by_ref("13441")
    assert ram["breadcrumb"] == "Consumer Electronics > Computers & Accessories > Desktop & Laptop Components > Memory / RAM"
    assert MeeshoAdapter.template_by_ref(" consumer electronics>computers & accessories > desktop & laptop components > memory / ram ") is ram
    assert all(len(e["segments"]) == 4 for e in MeeshoAdapter.template_index()["entries"])
    # Near-duplicate leaves stay two templates
    boxes = MeeshoAdapter.template_by_ref("Men Fashion > Accessories > Watches > Watch Boxes")
    boxes2 = MeeshoAdapter.template_by_ref("Men Fashion > Accessories > Watches > Watchboxes")
    assert boxes and boxes2 and boxes["id"] != boxes2["id"]
    assert MeeshoAdapter.template_by_ref("Bedsheets") is None and MeeshoAdapter.template_by_ref("99999") is None


@pytest.fixture
def clean_category_defaults():
    from app.services.settings_service import SettingsService
    yield SettingsService
    for category in SettingsService.get_meesho_category_defaults():
        SettingsService.set_meesho_category_default(category, None)


def test_a_category_default_places_its_products_and_a_product_choice_wins(clean_category_defaults):
    item = bedsheet("BS-DF-1", "Default bedsheet", **{"Meesho Category": None})
    assert MeeshoAdapter.resolve_item_template(item)[0] is None
    clean_category_defaults.set_meesho_category_default("bedsheets", "12776")  # any case of the category
    tmpl, _ = MeeshoAdapter.resolve_item_template(item)
    assert tmpl["id"] == "12776" and MeeshoAdapter.meesho_choice(item) == ("12776", "category")
    item["attributes"]["Meesho Category"] = "10058"  # the Kids & Toys bedsheets, chosen for this product
    assert MeeshoAdapter.resolve_item_template(item)[0]["id"] == "10058"
    assert MeeshoAdapter.meesho_choice(item) == ("10058", "product")


def test_a_choice_that_names_no_template_is_reported_not_guessed(clean_category_defaults):
    clean_category_defaults.set_meesho_category_default("Bedsheets", "99999")
    item = bedsheet("BS-DF-2", "Stale default bedsheet", **{"Meesho Category": None})
    problems = export_problems([item], category="Bedsheets")
    assert "'99999' (the default for 'Bedsheets') is not an official Meesho category" in problems[0]["reason"]


def test_taxonomy_endpoint_gives_the_panels_four_levels_with_template_ids():
    body = client.get("/api/v1/drafts/meesho/taxonomy").json()
    assert body["separator"] == " > "
    home = next(n for n in body["tree"] if n["name"] == "Home & Kitchen")
    furnishings = next(n for n in home["children"] if n["name"] == "Home Furnishings")
    bedding = next(n for n in furnishings["children"] if n["name"] == "Bedding & Linen")
    assert {"name": "Bedsheets", "id": "12776"} in bedding["children"]


def test_category_defaults_endpoint_saves_validates_and_clears(clean_category_defaults):
    url = "/api/v1/drafts/meesho/category-defaults"
    assert client.put(url, json={"category": "Bedsheets", "meesho_category": "Home & Kitchen > Bedsheets"}).status_code == 422
    res = client.put(url, json={"category": "Bedsheets", "meesho_category": "Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets"})
    assert res.status_code == 200
    row = next(r for r in res.json()["defaults"] if r["category"] == "Bedsheets")
    assert row["id"] == "12776" and row["breadcrumb"].endswith("> Bedsheets") and row["products"] >= 5
    cleared = client.put(url, json={"category": "Bedsheets", "meesho_category": ""}).json()["defaults"]
    assert next(r for r in cleared if r["category"] == "Bedsheets")["id"] is None


def test_templates_are_listed_without_opening_them():
    MeeshoAdapter.template_index(force_refresh=True)
    listed = MeeshoAdapter.get_available_templates()
    assert len(listed) > 3000 and {"id", "category", "breadcrumb", "filename"} == set(listed[0])
    assert MeeshoAdapter._loaded_templates == {}
    MeeshoAdapter.find_template(BEDSHEETS)
    assert len(MeeshoAdapter._loaded_templates) == 1


def test_sole_material_and_weave_pattern_are_not_filled_from_other_attributes():
    tmpl = MeeshoAdapter.find_template(SNEAKERS)
    row = {"attrs": {"Material": "Canvas", "Pattern": "Solid"}}
    assert MeeshoAdapter._template_value("material", "Material", row, "Sneakers") == "Canvas"
    assert MeeshoAdapter._template_value("sole material", "Sole Material", row, "Sneakers") is None
    assert MeeshoAdapter._template_value("weave pattern", "Weave Pattern", row, "Shirts") is None
    assert MeeshoAdapter._template_value("pattern", "Pattern", row, "Shirts") == "Solid"
    assert tmpl is not None


def test_several_categories_always_zip():
    buf, media_type, _ = MeeshoAdapter.generate_batch_export([tshirt("TS-7", "Zip tee"), bedsheet("BS-3", "Zip bedsheet")])
    assert media_type == "application/zip"
    zf = zipfile.ZipFile(buf)
    assert sorted(zf.namelist()) == ["ListingPilot_Meesho_Bedsheets.xlsx", "ListingPilot_Meesho_Tshirts.xlsx", "UPLOAD_CHECKLIST.txt"]
    checklist = zf.read("UPLOAD_CHECKLIST.txt").decode()
    # Each file with the exact category to pick in the supplier panel and its SKUs
    assert "Category: Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets  (template 12776)" in checklist
    assert "1 product(s): BS-3" in checklist and "Import error / warning file" in checklist


def test_two_templates_sharing_a_name_get_their_own_files():
    women = tshirt("TS-W1", "Women tee", **{"Meesho Category": "Women Fashion/Western Wear/Tops, Tshirts & Shirts/Tshirts"})
    with patch.object(MeeshoAdapter, "populate_template", side_effect=lambda t, items: io.BytesIO(t["path"].encode())):
        buf, media_type, _ = MeeshoAdapter.generate_batch_export([tshirt("TS-M1", "Men tee"), women])
    zf = zipfile.ZipFile(buf)
    files = [n for n in zf.namelist() if n.endswith(".xlsx")]
    assert media_type == "application/zip" and len(files) == 2
    # Each file is named with its template's own id, so neither overwrites the other
    assert all(re.fullmatch(r"ListingPilot_Meesho_Tshirts_\d+\.xlsx", n) for n in files)
    assert {zf.read(n).decode() for n in files} == {TSHIRTS, women["attributes"]["Meesho Category"]}


def test_fill_in_sheet_round_trips_through_catalogue_import():
    item = bedsheet("BS-4", "Round trip bedsheet", **{"HSN ID": None, "Color": None, "Quality": None})
    wb = openpyxl.load_workbook(MeeshoAdapter.build_fill_in_sheet([item]))
    ws = wb["Fill in"]
    headers = [c.value for c in ws[1]]
    assert {"Meesho HSN ID", "Meesho Color", "Meesho Quality"} <= set(headers)
    assert ws.data_validations.dataValidation  # dropdowns carry the template's own options

    # Seller fills the gaps, the sheet is imported, and the export now passes
    filled = {"Meesho HSN ID": "63041910", "Meesho Color": "Blue", "Meesho Quality": "Regular"}
    for name, value in filled.items():
        ws.cell(row=2, column=headers.index(name) + 1, value=value)
    out = io.BytesIO()
    wb.save(out)
    parsed, errors, _ = CatalogueParser.parse_file("fill.xlsx", out.getvalue())
    assert not errors and parsed[0]["sku"] == "BS-4"
    item["attributes"].update(parsed[0]["attributes"])
    item["images"] = parsed[0]["images"]
    MeeshoAdapter.generate_batch_export([item], category_filter="Bedsheets")


def test_fill_in_sheet_is_none_when_nothing_is_missing():
    assert MeeshoAdapter.build_fill_in_sheet([bedsheet("BS-5", "Complete bedsheet")]) is None


def test_export_endpoint_reports_problems_with_422():
    res = client.get("/api/v1/drafts/meesho/export?category=Bedsheets")
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert "blocked" in detail["message"]
    assert any(p["sku"] == "JBP-101" for p in detail["problems"])


def _with_meesho_draft(product_id, title, approved=True):
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        db.query(ListingDraft).filter(ListingDraft.product_id == product_id, ListingDraft.marketplace == "meesho").delete()
        db.add(ListingDraft(product_id=product_id, marketplace="meesho", title=title, bullets=["SOFT COTTON — breathable"],
                            description="Plain black tee.", is_approved=approved, status="approved" if approved else "draft"))
        db.commit()
    finally:
        db_gen.close()


def test_export_endpoint_streams_the_selected_products():
    pid = _test_db_product(tshirt("TS-API-1", "Endpoint tee"))
    _with_meesho_draft(pid, "Endpoint tee")
    res = client.get(f"/api/v1/drafts/meesho/export?product_ids={pid}")
    assert res.status_code == 200, res.text
    assert sheet_row(io.BytesIO(res.content))["SKU ID"] == "TS-API-1"
    # Exported, never "live": nothing is on Meesho until its processed file says so
    draft = client.get(f"/api/v1/drafts/product/{pid}?marketplace=meesho").json()
    assert draft["status"] == "exported" and draft["is_approved"] and draft["last_sync_at"]


def test_readiness_and_export_check_the_selection_together():
    ready = _test_db_product(tshirt("TS-RD-1", "Ready tee"))
    _with_meesho_draft(ready, "Ready tee")
    unapproved = _test_db_product(tshirt("TS-RD-2", "Unapproved tee"))
    _with_meesho_draft(unapproved, "Unapproved tee", approved=False)

    body = client.get(f"/api/v1/drafts/meesho/readiness?product_ids={ready},{unapproved}").json()
    by_sku = {r["sku"]: r for r in body["products"]}
    assert (body["ready"], body["total"]) == (1, 2)
    assert by_sku["TS-RD-1"]["ready"] and by_sku["TS-RD-1"]["meesho_category"].endswith("> Tshirts")
    assert [p["field"] for p in by_sku["TS-RD-2"]["problems"]] == ["Meesho Draft"]

    blocked = client.get(f"/api/v1/drafts/meesho/export?product_ids={ready},{unapproved}")
    assert blocked.status_code == 422 and "1 of 2 product(s)" in blocked.json()["detail"]["message"]
    assert client.get(f"/api/v1/drafts/meesho/export?product_ids={ready}").status_code == 200  # taken out, it exports
    assert client.get("/api/v1/drafts/meesho/export?product_ids=999999").status_code == 404  # never silently dropped


def test_words_meesho_flags_block_approval():
    product = Product(sku="X", name="x", category="Bedsheets", price=100, attributes={}, images=["a"], image_count=1)
    draft = {"title": "A cotton bedsheet set", "bullets": ["CARE — machine wash"], "description": "Soft comfort."}
    issues = RuleEngine.evaluate(product, draft, marketplace="meesho")["issues"]
    flagged = [i for i in issues if i["kind"] == "meesho_flagged_word"]
    assert flagged and flagged[0]["level"] == "error"
    assert not [i for i in RuleEngine.evaluate(product, draft, marketplace="amazon")["issues"] if i["kind"] == "meesho_flagged_word"]


def test_required_attributes_match_whatever_case_the_import_stored():
    # The importer title-cases headers: a sheet's "Thread count" column is stored as "Thread Count"
    attrs = {"Material": "Cotton", "Size": "90 x 100 in", "Thread Count": "180 TC", "Care": "Machine wash"}
    product = Product(sku="X", name="x", category="Bedsheets", price=100, attributes=attrs, images=["a"], image_count=1)
    issues = RuleEngine.evaluate(product, None, marketplace="amazon")["issues"]
    assert not [i for i in issues if i["kind"] == "attribute"]


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


def _test_db_product(item):
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        product = db.query(Product).filter(Product.sku == item["sku"]).first()
        if product:
            db.delete(product)
            db.commit()
        product = Product(**{k: item[k] for k in ["sku", "name", "category", "brand", "price", "mrp", "stock", "attributes", "images"]})
        db.add(product)
        db.commit()
        return product.id
    finally:
        db_gen.close()


def test_missing_fields_endpoint_lists_what_the_export_needs():
    pid = _test_db_product(bedsheet("BS-MF-1", "Missing fields bedsheet", **{"Meesho Size": None, "Quality": None}))
    res = client.get(f"/api/v1/drafts/meesho/missing-fields/{pid}")
    assert res.status_code == 200
    fields = {f["field"]: f for f in res.json()["fields"]}
    assert set(fields) == {"Size", "Quality"}
    assert fields["Size"]["attribute"] == "Meesho Size"
    assert fields["Size"]["options"] == ["Crib", "Double King", "Double Queen", "Single"]


def test_saving_missing_fields_merges_only_valid_template_values():
    pid = _test_db_product(bedsheet("BS-MF-2", "Saving fields bedsheet", **{"Meesho Size": None, "Quality": None}))
    url = f"/api/v1/drafts/meesho/missing-fields/{pid}"

    # A value outside the template's options (or an unknown field) saves nothing at all
    bad = client.put(url, json={"values": {"Meesho Size": "double queen", "Meesho Quality": "Regular"}})
    assert bad.status_code == 422
    assert {f["field"] for f in client.get(url).json()["fields"]} == {"Size", "Quality"}
    assert client.put(url, json={"values": {"Thread Colour": "Red"}}).status_code == 422

    ok = client.put(url, json={"values": {"Meesho Size": "Double Queen", "Meesho Quality": "Regular"}})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["product"]["attributes"]["Meesho Size"] == "Double Queen"
    assert body["product"]["attributes"]["Size"] == "90 x 100 in (double)"  # other attributes untouched
    # Every field is in; what's left is the copy, which no value can supply
    assert body["missing"]["fields"] == [] and [o["field"] for o in body["missing"]["other"]] == ["Meesho Draft"]


def test_missing_fields_for_a_category_without_template():
    pid = _test_db_product(no_template_item("PJ-MF-1", "Diya without template"))
    url = f"/api/v1/drafts/meesho/missing-fields/{pid}"
    assert client.get(url).json()["template"] is None
    assert client.put(url, json={"values": {"Color": "Red"}}).status_code == 422
    # Only an official template's path is accepted as the Meesho Category
    assert client.put(url, json={"values": {"Meesho Category": "Home & Kitchen/Diyas"}}).status_code == 422
    ok = client.put(url, json={"values": {"Meesho Category": "home & kitchen > home decor > puja accessories > puja articles"}})
    assert ok.status_code == 200, ok.text
    saved_id = ok.json()["product"]["attributes"]["Meesho Category"]
    assert MeeshoAdapter.template_by_ref(saved_id)["breadcrumb"] == "Home & Kitchen > Home Decor > Puja Accessories > Puja Articles"  # saved as the template id
    chosen = client.get(url).json()["meesho_category"]
    assert (chosen["id"], chosen["breadcrumb"], chosen["source"]) == (saved_id, "Home & Kitchen > Home Decor > Puja Accessories > Puja Articles", "product")
    # Empty removes the product's own choice
    cleared = client.put(url, json={"values": {"Meesho Category": ""}})
    assert cleared.status_code == 200 and "Meesho Category" not in cleared.json()["product"]["attributes"]
    assert cleared.json()["missing"]["template"] is None


def test_full_catalog_request_gets_a_zip_even_for_one_category():
    buf, media_type, filename = MeeshoAdapter.generate_batch_export([tshirt("TS-Z1", "Lone tee")], force_zip=True)
    assert media_type == "application/zip" and filename.endswith(".zip")
    assert zipfile.ZipFile(buf).namelist() == ["ListingPilot_Meesho_Tshirts.xlsx", "UPLOAD_CHECKLIST.txt"]


SELLER = {k: LEGAL[k] for k in LEGAL}


@pytest.fixture
def seller_details_in_settings():
    from app.services.settings_service import SettingsService
    SettingsService.update_seller_details(SELLER)
    yield
    SettingsService.update_seller_details({k: "" for k in SELLER})


def test_seller_details_come_from_settings_when_the_product_has_none(seller_details_in_settings):
    bare = bedsheet("BS-SD-1", "Settings bedsheet", **{k: None for k in LEGAL})
    buf, _, _ = MeeshoAdapter.generate_batch_export([bare], category_filter="Bedsheets")
    row = bedsheet_row(buf)
    assert row["Manufacturer Name"] == "Rangrez Textiles" and row["Importer Pincode"] == "641604"
    assert row["Country of Origin"] == "India"


def test_a_products_own_value_beats_settings(seller_details_in_settings):
    own = bedsheet("BS-SD-2", "Own maker bedsheet", **{"Manufacturer Name": "Sanganer Prints"})
    buf, _, _ = MeeshoAdapter.generate_batch_export([own], category_filter="Bedsheets")
    assert bedsheet_row(buf)["Manufacturer Name"] == "Sanganer Prints"


def test_missing_seller_details_point_to_settings_not_each_product():
    bare = bedsheet("BS-SD-3", "Bare bedsheet", **{k: None for k in LEGAL})
    missing = MeeshoAdapter.missing_fields(bare)
    assert set(missing["seller"]) == set(LEGAL) and missing["fields"] == []
    headers = [c.value for c in openpyxl.load_workbook(MeeshoAdapter.build_fill_in_sheet([bare]))["Fill in"][1]]
    assert not set(LEGAL) & set(headers)


def test_seller_details_endpoint_validates_before_saving():
    url = "/api/v1/settings/seller-details"
    assert client.put(url, json={"Manufacturer Pincode": "64160"}).status_code == 422
    assert client.put(url, json={"Brand": "Gulmohar"}).status_code == 422
    assert client.get(url).json()["Manufacturer Pincode"] == ""  # nothing was saved
    saved = client.put(url, json={"Manufacturer Name": " Rangrez Textiles "}).json()
    assert saved["Manufacturer Name"] == "Rangrez Textiles"
    client.put(url, json={"Manufacturer Name": ""})


def blocking(items):
    """The blocking problems of an export that must fail (Brand's optional, never-guessed dropdown aside)."""
    return [p for p in export_problems(items) if p["blocking"]]


def test_unapproved_or_missing_meesho_copy_blocks_the_export():
    unapproved = tshirt("TS-G1", "Unapproved tee")
    unapproved["draft"]["is_approved"] = False
    no_draft = tshirt("TS-G2", "Draftless tee")
    no_draft["draft"] = None
    problems = blocking([unapproved, no_draft])
    assert {(p["sku"], p["field"]) for p in problems} == {("TS-G1", "Meesho Draft"), ("TS-G2", "Meesho Draft")}


def test_a_long_title_blocks_instead_of_being_cut():
    problems = blocking([tshirt("TS-G3", "Plain black cotton tee " * 5)])
    assert [p["field"] for p in problems] == ["Product Name"] and "Meesho allows 100" in problems[0]["reason"]


@pytest.mark.parametrize("title, blocked", [
    ("Cotton bedsheet 90 x 100", "a dimension"),
    ("Brass urli bowl 10 inch", "a dimension"),
    ("Steel bottle 750 gm", "a weight"),
    ("Cotton tee ₹499", "a price"),
    ("Amazon style cotton tee", "another marketplace's name"),
    ("2 in 1 cotton tee", None),  # 'in' here isn't inches
    ("5G phone print cotton tee", None),
    ("Cotton tee pack of 2", None),
])
def test_product_name_keeps_out_weight_dimensions_price_and_portals(title, blocked):
    by_sku = MeeshoAdapter.check_items([tshirt("TS-G4", title)])
    reasons = [p["reason"] for p in by_sku["TS-G4"] if p["field"] == "Product Name"]
    assert (reasons[0].startswith(f"contains {blocked}") if blocked else reasons == [])


def test_words_meesho_flags_block_the_export():
    flagged = tshirt("TS-G5", "Soft cotton tee")
    flagged["draft"]["description"] = "Easy care and all-day comfort."
    problems = blocking([flagged])
    assert [p["field"] for p in problems] == ["Product Description"] and "'care', 'comfort'" in problems[0]["reason"]


def test_price_rules_from_the_template():
    assert [p["field"] for p in blocking([{**tshirt("TS-G6", "Priced tee"), "price": 799.0}])] == ["Meesho Price"]
    discount = "Wrong/Defective Return Discount(₹)"
    assert [p["field"] for p in blocking([tshirt("TS-G7", "Discount tee", **{discount: "499"})])] == [discount]
    MeeshoAdapter.generate_batch_export([tshirt("TS-G8", "Fine discount tee", **{discount: "22"})])


@pytest.mark.parametrize("link, ok", [
    ("https://images.unsplash.com/photo-1", False),
    ("http://localhost:8000/static/uploads/a.jpg", False),
    ("https://drive.google.com/file/d/abc/view", False),
    # The seller's own storage: Meesho accepted a Supabase signed link (3 Nov 2026)
    ("https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/a.jpg?token=t", True),
    ("front.jpg", False),
    ("https://example.com/front.jpg", True),
])
def test_image_links_must_be_usable_by_meesho(link, ok):
    item = tshirt("TS-G9", "Linked tee")
    item["images"] = [link]
    by_sku = MeeshoAdapter.check_items([item])
    assert (not [p for p in by_sku["TS-G9"] if p["field"] == "Image 1 (Front)"]) == ok


PLANTER = "13367"  # Product Length/Breadth/Height + Product Unit (Cm, Inch...), Product Weight + Unit (G, Kg)
PUJA = "12811"     # the same sides, and 'Weight' with 'Weight Unit' (g, kg)


def measurements(template_id, **attrs):
    return MeeshoAdapter._measurements(attrs, MeeshoAdapter._load_template(MeeshoAdapter.template_by_ref(template_id)))


def test_one_stated_size_and_weight_fill_any_templates_measurement_columns():
    m = measurements(PLANTER, Dimensions="6 x 6 x 5.5 in", Weight="1.2 kg")
    assert (m["product length"], m["product breadth"], m["product height"], m["product unit"]) == (6, 6, 5.5, "Inch")
    assert (m["product weight"], m["product weight unit"]) == (1.2, "Kg")
    m = measurements(PUJA, Dimensions="20 x 15 x 10 cm", Weight="350 g (set)")
    assert (m["product length"], m["product breadth"], m["product unit"]) == (20, 15, "cm")
    assert (m["weight"], m["weight unit"]) == (350, "g")


def test_a_weight_the_template_doesnt_list_is_left_to_the_seller():
    # 480 g is neither a listed gram amount nor a listed kg amount (0.48); it's never rounded
    m = measurements(PLANTER, Weight="480 g")
    assert "product weight" not in m and "product weight unit" not in m


def test_cm_columns_and_spelled_weights_use_the_stated_values():
    tmpl = {"columns": {1: "Product Length (cm)", 2: "Product Dimensions (L x B x H) in cm", 3: "Weight"},
            "dropdowns": {3: ["100gm", "1.5kg", "500gm"]}}
    m = MeeshoAdapter._measurements({"Dimensions": "10 x 4 x 2 in", "Weight": "0.5 kg"}, tmpl)
    assert m["product length (cm)"] == 25.4 and m["product dimensions (l x b x h) in cm"] == "25.4 x 10.2 x 5.1"
    assert m["weight"] == "500gm"
    assert MeeshoAdapter._measurements({"Weight": "1500 g"}, tmpl)["weight"] == "1.5kg"


@pytest.mark.parametrize("text, expected", [
    ("6 x 6 x 5.5 in", ([6, 6, 5.5], "inch")),
    ("90 x 100 in (double)", ([90, 100], "inch")),
    ("30x20x10cm", ([30, 20, 10], "cm")),
    ("Single, 60 x 90 in", ([60, 90], "inch")),
    ("4 x 4 x 2.5 in each", ([4, 4, 2.5], "inch")),
    ("3.5 x 3.5 in each pot, tray 11 x 4 in", None),  # two items: which is the product?
    ("10 in diameter x 3.5 in depth", None),
    ("18 in total hang length (Bell 4 in)", None),
    ("M (Bust 38 in)", None),
])
def test_only_a_clearly_stated_size_is_read(text, expected):
    from app.services.meesho_adapter import _stated_dimensions
    assert _stated_dimensions(text) == expected


def test_a_meesho_value_for_any_column_wins_over_the_descriptive_attribute():
    tee = tshirt("TS-MV-1", "Meesho value tee", **{"Meesho Fabric": "Polyester", "Meesho Color": "White"})
    row = sheet_row(MeeshoAdapter.generate_batch_export([tee], category_filter="Tshirts")[0])
    assert (row["Fabric"], row["Color"]) == ("Polyester", "White")
    assert MeeshoAdapter.seller_fields(MeeshoAdapter.find_template(TSHIRTS))["Meesho Fabric"]["field"] == "Fabric"


def bedsheet_product(**attrs):
    return Product(sku="JBP-F1", name="Indigo floral double bedsheet", category="Bedsheets", brand="Gulmohar Home",
                   price=1299, attributes={"Meesho Category": "12776", "Material": "Cotton",
                                           "Size": "90 x 100 in (double)", "Colour": "Indigo and white", **attrs})


def fact_issues(product, **copy):
    draft = {"title": "Gulmohar Home Indigo Floral Cotton Double Bedsheet", "bullets": [], "description": "", **copy}
    return [i for i in RuleEngine.meesho_copy_issues(product, draft) if i["kind"] in ("unsupported_fact", "puffery")]


def test_copy_stating_only_the_data_passes_the_fact_check():
    assert fact_issues(bedsheet_product(), description="Cotton double bedsheet in indigo and white, 90 x 100 in.") == []


@pytest.mark.parametrize("description, unsupported", [
    ("Made of 100% pure cotton.", ["'100%'", "'pure'"]),
    ("Measures 228 x 254 cm.", ["228", "254"]),  # a conversion the data doesn't state
    ("A polyester bedsheet.", ["'Polyester'"]),  # the template's fabric, not this product's
    ("Handmade by artisans.", ["'handmade'"]),
    ("Machine wash cold.", ["'machine wash'"]),
])
def test_copy_inventing_facts_is_an_error(description, unsupported):
    errors = " ".join(i["message"] for i in fact_issues(bedsheet_product(), description=description) if i["level"] == "error")
    assert all(u in errors for u in unsupported), errors


def test_a_claim_the_data_states_is_allowed_and_praise_only_warns():
    product = bedsheet_product(Care="Machine wash cold", Material="100% cotton")
    assert fact_issues(product, description="100% cotton. Machine wash cold.") == []
    issues = fact_issues(bedsheet_product(), description="A premium, durable cotton bedsheet.")
    assert [i["level"] for i in issues] == ["warning"] and "'premium', 'durable'" in issues[0]["message"]


def test_meesho_approval_needs_the_templates_compulsory_fields():
    attrs = bedsheet("BS-RQ-1", "x", Quality=None)["attributes"]
    product = Product(sku="BS-RQ-1", name="Bedsheet", category="Bedsheets", brand="Gulmohar Home", price=499, mrp=799,
                      stock=12, attributes=attrs, images=["https://example.com/a.jpg"], image_count=1)
    issues = RuleEngine.evaluate(product, None, marketplace="meesho")["issues"]
    assert [i["field"] for i in issues if i["kind"] == "attribute"] == ["Quality"]
    product.attributes = {k: v for k, v in attrs.items() if k != "Meesho Category"}
    issues = RuleEngine.evaluate(product, None, marketplace="meesho")["issues"]
    errors = [i for i in issues if i["level"] == "error"]
    assert [i["kind"] for i in errors] == ["meesho_category"] and "suggested:" in errors[0]["message"]


def _groq(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_test_key")


INVENTED = {"title": "Gulmohar Home Pure Cotton Bedsheet", "bullets": ["FABRIC — Pure cotton"], "description": "Pure cotton.", "keywords": []}
FACTUAL = {"title": "Gulmohar Home Indigo Floral Cotton Double Bedsheet", "bullets": ["FABRIC — Cotton"],
           "description": "Cotton double bedsheet.", "keywords": []}


def test_meesho_copy_inventing_facts_is_regenerated_with_the_failures_listed(monkeypatch):
    _groq(monkeypatch)
    fake = AsyncMock(side_effect=[dict(INVENTED), dict(FACTUAL)])
    with patch.object(AIService, "_call_chat_completions", fake):
        content = asyncio.run(AIService.generate_listing(bedsheet_product(), marketplace="meesho"))
    assert content == FACTUAL and fake.call_count == 2
    assert "'pure'" in fake.call_args_list[1].args[5] and "'pure'" not in fake.call_args_list[0].args[5]


def test_regeneration_stops_after_two_retries(monkeypatch):
    _groq(monkeypatch)
    fake = AsyncMock(side_effect=lambda *a, **k: dict(INVENTED))
    with patch.object(AIService, "_call_chat_completions", fake):
        content = asyncio.run(AIService.generate_listing(bedsheet_product(), marketplace="meesho"))
    assert fake.call_count == 3 and content["title"] == INVENTED["title"]  # left for the seller to fix


def test_meesho_prompt_is_built_from_the_template_and_the_data_only(monkeypatch):
    _groq(monkeypatch)
    fake = AsyncMock(return_value={"title": "t"})
    with patch.object(AIService, "_call_chat_completions", fake):
        asyncio.run(AIService.generate_listing(bedsheet_product(), marketplace="meesho"))
    system_prompt, user_prompt = fake.call_args.args[4], fake.call_args.args[5]
    assert "Meesho category: Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets" in user_prompt
    assert "Shoppers filter this Meesho category by:" in user_prompt and "Fabric" in user_prompt
    assert "No size, weight, dimension, price or marketplace name" in system_prompt
    assert "Never convert units" in system_prompt and "Hinglish" in system_prompt
    assert "12776" not in user_prompt and "₹" not in user_prompt  # neither the template id nor the price is copy
    assert "flagship" not in system_prompt and "premium" not in user_prompt


def test_template_copy_for_meesho_states_only_the_data():
    product = bedsheet_product()
    content = AIService._fallback_generator(product, "Gulmohar Home", marketplace="meesho")
    assert "90 x 100" not in content["title"] and not content["title"].endswith("...")
    assert not [i for i in RuleEngine.meesho_copy_issues(product, content) if i["level"] == "error"]
    assert "Authentic" not in " ".join(content["bullets"]) and "verified" not in content["description"].lower()


def test_approval_rechecks_the_product_as_it_is_now():
    pid = _test_db_product(tshirt("TS-AP-1", "Approval tee", **{"Meesho Category": None}))
    _with_meesho_draft(pid, "Gulmohar Home Black Cotton Tee", approved=False)  # stored without rule results
    draft_id = client.get(f"/api/v1/drafts/product/{pid}?marketplace=meesho").json()["id"]
    refused = client.post(f"/api/v1/drafts/{draft_id}/approve")
    assert refused.status_code == 400 and "Meesho category" in refused.json()["detail"]
    saved = client.put(f"/api/v1/drafts/meesho/missing-fields/{pid}", json={"values": {"Meesho Category": "10000"}})
    assert saved.status_code == 200 and saved.json()["draft"]["rule_results"]["has_errors"] is False
    approved = client.post(f"/api/v1/drafts/{draft_id}/approve")
    assert approved.status_code == 200, approved.text


def test_a_descriptive_weight_named_like_the_column_is_read_as_amount_and_unit():
    # Puja Articles has a 'Weight' column: 'Weight: 350 g' is the stated weight, not a template value
    tmpl = MeeshoAdapter._load_template(MeeshoAdapter.template_by_ref(PUJA))
    row = {"attrs": {"Weight": "350 g (set)"}, "measures": MeeshoAdapter._measurements({"Weight": "350 g (set)"}, tmpl)}
    assert MeeshoAdapter._template_value("weight", "Weight", row, "Puja Articles") == 350
    assert MeeshoAdapter._template_value("weight unit", "Weight Unit", row, "Puja Articles") == "g"
    # The seller's exact Meesho value still wins
    row["attrs"]["Meesho Weight"] = "0.4"
    assert MeeshoAdapter._template_value("weight", "Weight", row, "Puja Articles") == "0.4"


def test_each_product_gets_its_own_group_id_and_sizes_share_one():
    # One Group ID for every row made Meesho merge five bedsheets into one product (processed file, 30 Oct)
    items = [bedsheet("BS-G1", "First group bedsheet"), bedsheet("BS-G2", "Second group bedsheet"),
             bedsheet("BS-G3", "Sized group bedsheet", **{"Style ID": "BS-G3"}),
             bedsheet("BS-G3-K", "Sized group bedsheet", **{"Style ID": "BS-G3", "Meesho Variation": "King",
                                                              "Meesho Size": "Double King", "Size": "108 x 108 in (king)"}),
             bedsheet("BS-G4", "Own group bedsheet", **{"Meesho Group ID": "Group 09"})]
    buf, _, _ = MeeshoAdapter.generate_batch_export(items, category_filter="Bedsheets")
    groups = [bedsheet_row(buf, r)["Group ID"] for r in range(5, 10)]
    assert groups == ["Group 01", "Group 02", "Group 03", "Group 03", "Group 09"]


@pytest.mark.parametrize("description", [
    "Maroon and beige cotton.",          # brand 'Maroon' on Meesho's list (processed file, 3 Nov 2026)
    "A lotus print bedsheet.",           # 'Lotus Herbals'
    "This is an indigo bedsheet.",       # 'An'
    "Fits a 10 in drop.",                # 'SmartDrops'
])
def test_words_meesho_matches_to_brands_block_the_export(description):
    tee = tshirt("TS-BR1", "Brand word tee")
    tee["draft"]["description"] = description
    assert [p["field"] for p in blocking([tee])] == ["Product Description"]


@pytest.mark.parametrize("description, blocked", [
    ("Shoppers also refer to it as a chadar.", True),     # a note to the reader, not product copy
    ("Search for bedsheet to find similar styles.", True),
    ("Cotton double bedsheet, also called a chadar.", False),
    ("Cotton double bedsheet, बिस्तर की चादर.", True),       # Hinglish belongs in English letters
    ("Hand‑polished “gold” finish — ₹ value.", False),     # typographic dashes, quotes and ₹ are fine
])
def test_meesho_copy_is_about_the_product_in_english_letters(description, blocked):
    issues = RuleEngine.meesho_copy_issues(bedsheet_product(), {"title": "Gulmohar Home Cotton Double Bedsheet",
                                                                "bullets": [], "description": description})
    assert any(i["kind"] == "copy_style" and i["level"] == "error" for i in issues) == blocked


def test_meesho_prompt_keeps_search_terms_inside_product_sentences(monkeypatch):
    _groq(monkeypatch)
    fake = AsyncMock(return_value={"title": "t"})
    with patch.object(AIService, "_call_chat_completions", fake):
        asyncio.run(AIService.generate_listing(bedsheet_product(), marketplace="meesho"))
    system_prompt = fake.call_args.args[4]
    assert "never mention shoppers, searching or keywords" in system_prompt
    assert "written in English letters" in system_prompt and '"HEADLINE — fact"' in system_prompt


def processed_file(items, results, extra_rows=()):
    """A processed file as the supplier panel returns it: our upload with ERROR STATUS / ERROR MESSAGE filled in."""
    buf, _, _ = MeeshoAdapter.generate_batch_export(items)
    wb = openpyxl.load_workbook(buf)
    tmpl = MeeshoAdapter.find_template(TSHIRTS)
    ws = wb[tmpl["sheet_name"]]
    col = {name: idx for idx, name in tmpl["columns"].items()}
    last = 4
    for r in range(5, ws.max_row + 1):
        sku = ws.cell(r, col["SKU ID"]).value
        if not sku:
            continue
        last = r
        status, message = results.get(sku, ("", ""))
        ws.cell(r, col["ERROR STATUS"], value=status or None)
        ws.cell(r, col["ERROR MESSAGE"], value=message or None)
    for sku, status, message in extra_rows:
        last += 1
        ws.cell(last, col["SKU ID"], value=sku)
        ws.cell(last, col["ERROR STATUS"], value=status)
        ws.cell(last, col["ERROR MESSAGE"], value=message)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_a_processed_file_gives_each_sku_its_result_and_flagged_words():
    content = processed_file([tshirt("TS-QP-1", "Flagged tee"), tshirt("TS-QP-2", "Clean tee")], {
        # As Meesho writes it (processed file, 3 Nov 2026): keywords after a sentence too
        "TS-QP-1": ("INVALID", "Maroon(Warning), velvetine(Warning)  detected in PRODUCT NAME. maroon(Warning)  "
                               "detected in PRODUCT DESCRIPTION. Error keywords are not allowed"),
    })
    rows = {r["sku"]: r for r in MeeshoAdapter.parse_processed_file(content)}
    assert rows["TS-QP-1"]["passed"] is False and rows["TS-QP-1"]["keywords"] == ["maroon", "velvetine"]
    assert rows["TS-QP-2"]["passed"] is True and rows["TS-QP-2"]["keywords"] == []


@pytest.mark.parametrize("content, reason", [
    (b"SKU,Status\nX,1\n", "Not an Excel"),
    (None, "No '<Category>-Fill this' sheet"),
])
def test_a_file_that_isnt_a_processed_file_is_refused(content, reason):
    if content is None:
        wb, out = openpyxl.Workbook(), io.BytesIO()
        wb.save(out)
        content = out.getvalue()
    with pytest.raises(ValueError, match=re.escape(reason)):
        MeeshoAdapter.parse_processed_file(content)


def test_importing_a_processed_file_sends_failed_drafts_back_and_learns_words():
    failing = _test_db_product(tshirt("TS-QC-1", "Velvetine tee"))
    _with_meesho_draft(failing, "Gulmohar Home Velvetine Black Cotton Tee")
    passing = _test_db_product(tshirt("TS-QC-2", "Passing tee"))
    _with_meesho_draft(passing, "Gulmohar Home Plain Cotton Tee")
    content = processed_file([tshirt("TS-QC-1", "Velvetine tee"), tshirt("TS-QC-2", "Passing tee")], {
        "TS-QC-1": ("INVALID", "velvetine(Warning)  detected in PRODUCT DESCRIPTION. Error keywords are not allowed"),
    }, extra_rows=[("NOT-IN-CATALOGUE", "INVALID", "whatever")])

    res = client.post("/api/v1/drafts/meesho/processed-file",
                      files={"file": ("processed.xlsx", content, "application/octet-stream")})
    assert res.status_code == 200, res.text
    body = res.json()
    assert [f["sku"] for f in body["failed"]] == ["TS-QC-1"] and [p["sku"] for p in body["passed"]] == ["TS-QC-2"]
    assert body["unknown_skus"] == ["NOT-IN-CATALOGUE"] and "velvetine" in body["learned_words"]

    # The failed draft can't be exported until it's fixed and approved again; the reason is shown
    ready = {r["sku"]: r for r in client.get(f"/api/v1/drafts/meesho/readiness?product_ids={failing},{passing}").json()["products"]}
    assert not ready["TS-QC-1"]["ready"] and ready["TS-QC-1"]["qc_reason"].startswith("Meesho QC: velvetine")
    assert ready["TS-QC-2"]["ready"] and ready["TS-QC-2"]["qc_reason"] is None
    # The learned word now blocks copy that uses it
    product = Product(sku="X", name="x", category="Tshirts", price=1, attributes={}, images=[])
    assert any(i["kind"] == "meesho_flagged_word" for i in RuleEngine.meesho_copy_issues(
        product, {"title": "Velvetine tee", "bullets": [], "description": ""}))
    # The failed draft's own checks were rerun with the learned word, so the editor shows it at once
    draft = client.get(f"/api/v1/drafts/product/{failing}?marketplace=meesho").json()
    assert any(i["kind"] == "meesho_flagged_word" for i in draft["rule_results"]["issues"])
    # Fixed and approved, the QC reason is cleared
    draft_id = draft["id"]
    assert client.put(f"/api/v1/drafts/{draft_id}", json={"title": "Gulmohar Home Black Cotton Tee"}).status_code == 200
    assert client.post(f"/api/v1/drafts/{draft_id}/approve").status_code == 200
    assert client.get(f"/api/v1/drafts/product/{failing}?marketplace=meesho").json()["rejection_reason"] is None


def test_an_unreadable_processed_file_changes_nothing():
    res = client.post("/api/v1/drafts/meesho/processed-file", files={"file": ("errors.csv", b"a,b", "text/csv")})
    assert res.status_code == 422 and ".xlsx" in res.json()["detail"]
    res = client.post("/api/v1/drafts/meesho/processed-file", files={"file": ("errors.xlsx", b"not a workbook", "application/octet-stream")})
    assert res.status_code == 422 and "Not an Excel" in res.json()["detail"]
