import io
import json
import uuid
import openpyxl
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_export_formats():
    # 1. Export Excel
    res_xlsx = client.get("/api/v1/catalogue/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert "openxmlformats" in res_xlsx.headers["content-type"]
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.content))
    ws = wb.active
    assert ws.max_row > 50  # Contains our 50+ pilot SKUs

    # 2. Export CSV
    res_csv = client.get("/api/v1/catalogue/export?format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    csv_text = res_csv.content.decode("utf-8-sig")
    assert "SKU,Product Name,Category" in csv_text
    assert "JBP-101" in csv_text

    # 3. Export JSON
    res_json = client.get("/api/v1/catalogue/export?format=json")
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    data = json.loads(res_json.content)
    assert isinstance(data, list)
    assert len(data) >= 50
    assert any(p["sku"] == "JBP-101" for p in data)

def test_import_custom_csv():
    sku1 = f"IMP-{uuid.uuid4().hex[:6].upper()}"
    sku2 = f"IMP-{uuid.uuid4().hex[:6].upper()}"
    csv_content = f"""SKU,Product Name,Category,Brand,Selling Price,Stock,Material,Size
{sku1},Test Linen Cushion Cover,Home Decor,Gulmohar Home,499,30,Linen,16x16 in
{sku2},Embroidered Cotton Runner,Home Decor,Gulmohar Home,899,15,Cotton,14x72 in
"""
    files = {"file": ("test_import.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post("/api/v1/catalogue/import", files=files)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is True
    assert (res_json["imported_count"] + res_json["updated_count"]) == 2
    assert res_json["failed_count"] == 0

    # Verify products are queryable
    p1 = client.get(f"/api/v1/catalogue/products?search={sku1}").json()
    assert p1["total"] == 1
    assert p1["items"][0]["attributes"]["Material"] == "Linen"

def test_import_tally_xml():
    sku = f"TALLY-{uuid.uuid4().hex[:6].upper()}"
    xml_content = f"""<ENVELOPE>
      <BODY>
        <DATA>
          <TALLYMESSAGE>
            <STOCKITEM NAME="Tally Brass Bell Handcarved">
              <PARTNO>{sku}</PARTNO>
              <PARENT>Pooja items</PARENT>
              <RATE>650.00</RATE>
              <CLOSINGBALANCE>45</CLOSINGBALANCE>
            </STOCKITEM>
          </TALLYMESSAGE>
        </DATA>
      </BODY>
    </ENVELOPE>"""
    files = {"file": ("tally_export.xml", io.BytesIO(xml_content.encode("utf-8")), "application/xml")}
    response = client.post("/api/v1/catalogue/import", files=files)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is True
    assert (res_json["imported_count"] + res_json["updated_count"]) >= 1

    p = client.get(f"/api/v1/catalogue/products?search={sku}").json()
    assert p["total"] == 1
    assert p["items"][0]["price"] == 650.0
    assert p["items"][0]["stock"] == 45

def test_import_validation_errors():
    # A row without a SKU is reported and skipped; no SKU is made up from the name
    bad_csv = """SKU,Product Name,Category,Selling Price,Stock
,Bad Product Without SKU,General,100,5
"""
    files = {"file": ("bad.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")}
    response = client.post("/api/v1/catalogue/import", files=files)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is False
    assert res_json["failed_count"] == 1
    assert res_json["imported_count"] + res_json["updated_count"] == 0
    assert res_json["errors"][0]["field"] == "sku"
    assert client.get("/api/v1/catalogue/products?search=Bad Product Without SKU").json()["total"] == 0
