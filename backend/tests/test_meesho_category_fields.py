import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.settings_service import SELLER_DETAIL_FIELDS

client = TestClient(app)

BEDSHEETS = "12776"


def _fields(template_id=BEDSHEETS):
    res = client.get(f"/api/v1/drafts/meesho/category-fields/{template_id}")
    assert res.status_code == 200
    return res.json()


def test_lists_the_category_fields_with_required_ones_first():
    body = _fields()
    assert body["id"] == BEDSHEETS
    assert body["breadcrumb"] == "Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets"

    flags = [f["required"] for f in body["fields"]]
    assert True in flags and False in flags
    assert flags == sorted(flags, reverse=True)

    by_name = {f["field"]: f for f in body["fields"]}
    assert by_name["Thread Count"]["required"] is True
    assert by_name["Thread Count"]["attribute"] == "Meesho Thread Count"
    assert by_name["Thread Count"]["options"]
    assert by_name["Net Weight (gms)"]["options"] == []
    assert by_name["Net Weight (gms)"]["hint"]


def test_leaves_out_what_the_form_settings_or_export_already_fill():
    names = {f["field"] for f in _fields()["fields"]}
    covered = {"Product Name", "Meesho Price", "MRP", "Inventory", "Image 1 (Front)", "Image 2", "SKU ID", "Brand Name",
               "Product ID / Style ID", "Group ID", "Product Description", "ERROR STATUS", "ERROR MESSAGE",
               "Fields + Description:", *SELLER_DETAIL_FIELDS}
    assert not names & covered
    assert not any(n.startswith("Col_") for n in names)


def test_unknown_template_is_a_404_with_the_reason():
    res = client.get("/api/v1/drafts/meesho/category-fields/999999999")
    assert res.status_code == 404
    assert "999999999" in res.json()["detail"]


def test_values_saved_with_a_new_product_clear_those_fields_from_what_is_missing():
    fields = _fields()["fields"]
    first = next(f for f in fields if f["required"] and f["options"])
    product = client.post("/api/v1/catalogue/products", json={
        "sku": f"FORM-{uuid.uuid4().hex[:8]}", "name": "Form test bedsheet", "category": "Bedsheets",
        "price": 999, "stock": 5,
        "attributes": {"Meesho Category": BEDSHEETS, first["attribute"]: first["options"][0]},
    })
    assert product.status_code == 201

    missing = client.get(f"/api/v1/drafts/meesho/missing-fields/{product.json()['id']}").json()
    assert missing["meesho_category"]["id"] == BEDSHEETS
    still_missing = {f["field"] for f in missing["fields"]}
    assert first["field"] not in still_missing
    assert still_missing
