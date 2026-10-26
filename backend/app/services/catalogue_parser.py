import io
import csv
import re
import xml.etree.ElementTree as ET
import openpyxl
from typing import List, Dict, Any, Tuple
from app.schemas.import_export import RowValidationError

# Mapping of common column variants to normalized field names
# Mapping of common column variants to normalized field names
HEADER_MAPPINGS = {
    "sku": [
        "sku", "sku code", "item code", "product code", "part number", "part no", 
        "item no", "code", "barcode", "asin", "seller sku id", "seller sku id *", 
        "seller sku", "product id / sku", "style id"
    ],
    "name": [
        "product name", "item name", "title", "name", "product title", "item description", 
        "product", "particulars", "product name *", "item name *"
    ],
    "category": [
        "category", "cat", "product category", "item group", "group", "product type", 
        "department", "under", "stock group", "generic name"
    ],
    "brand": [
        "brand", "brand name", "manufacturer", "make", "brand name *", "manufacturer name *"
    ],
    "mrp": [
        "mrp", "m.r.p", "mrp (inr)", "maximum retail price", "list price", 
        "mrp (₹) *", "mrp (₹)", "mrp*"
    ],
    "price": [
        "selling price", "price", "rate", "sales rate", "selling price (inr)", 
        "our price", "offer price", "unit rate", "meesho price (₹) *", 
        "meesho price", "meesho price (₹)", "meesho selling price"
    ],
    "stock": [
        "stock", "stock quantity", "quantity", "qty", "closing balance", 
        "available qty", "closing qty", "units", "inventory", "inventory *"
    ],
    "images": [
        "images", "image urls", "image url", "photo urls", "photo url", 
        "photos", "image 1", "image_1", "image", "primary image url *", 
        "primary image url", "image 1 link"
    ]
}

KNOWN_ATTR_HEADERS = [
    "material", "size", "dimensions", "colour", "color", "pattern", "print", "finish", 
    "included", "included items", "care", "care instructions", "thread count", "weight", 
    "fit", "sleeve", "length", "closure", "drainage", "fill", "outer", "occasion", "notes",
    "gst rate (%) *", "gst rate", "hsn code *", "hsn code", "net weight (gms) *", "net weight",
    "country of origin *", "country of origin", "packer name", "color / finish", "wrong/defective price (₹) *"
]

def clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return s

def clean_num(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        return float(val)
    # Strip currency signs, commas, spaces
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned) if cleaned else default
    except ValueError:
        return default

class CatalogueParser:
    """Parses Excel, CSV, and Tally exports into normalized product dicts with validation."""

    @classmethod
    def parse_file(cls, filename: str, content: bytes) -> Tuple[List[Dict[str, Any]], List[RowValidationError], List[RowValidationError]]:
        """
        Parses an uploaded catalogue file.
        Returns (valid_products, errors, warnings).
        """
        lower_name = filename.lower()
        if lower_name.endswith(".xlsx") or lower_name.endswith(".xlsm") or lower_name.endswith(".xltx"):
            return cls._parse_excel(content)
        elif lower_name.endswith(".csv"):
            return cls._parse_csv(content)
        elif lower_name.endswith(".xml"):
            return cls._parse_tally_xml(content)
        else:
            raise ValueError(f"Unsupported file format: {filename}. Supported formats are .xlsx, .csv, and .xml (Tally export).")

    @classmethod
    def _parse_excel(cls, content: bytes) -> Tuple[List[Dict[str, Any]], List[RowValidationError], List[RowValidationError]]:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        # Select best sheet: priority to Meesho's 'Validate Sheet', 'Product Details', 'Master Catalogue'
        sheet = None
        priority_sheets = ["Validate Sheet", "Product Details", "Template", "Catalog", "Master Catalogue", "Products", "Sheet1"]
        for name in priority_sheets:
            for sname in wb.sheetnames:
                if sname.strip().lower() == name.lower():
                    sheet = wb[sname]
                    break
            if sheet:
                break
        if sheet is None:
            # Fallback: pick the sheet with the most rows
            sheet = max(wb.worksheets, key=lambda s: s.max_row)

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return [], [RowValidationError(row_number=1, field="file", message="The uploaded spreadsheet is empty.")], []

        # Find header row (usually row 1, or scan for a row containing 'sku' or 'name')
        header_idx = 0
        for i, row in enumerate(rows[:5]):
            row_str = " ".join([str(c).lower() for c in row if c is not None])
            if any(k in row_str for k in ["sku", "item code", "product name", "item name"]):
                header_idx = i
                break

        header_row = [clean_str(c).lower().replace("*", "").strip() for c in rows[header_idx]]
        data_rows = rows[header_idx + 1:]
        
        # Check if first data row is a hint row (e.g., "(Unique product SKU...)")
        if data_rows and any(str(c or '').strip().startswith("(") for c in data_rows[0]):
            data_rows = data_rows[1:]

        return cls._process_tabular_rows(header_row, data_rows, start_row=header_idx + 2)

    @classmethod
    def _parse_csv(cls, content: bytes) -> Tuple[List[Dict[str, Any]], List[RowValidationError], List[RowValidationError]]:
        # Detect encoding
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        f = io.StringIO(text)
        reader = list(csv.reader(f))
        if not reader:
            return [], [RowValidationError(row_number=1, field="file", message="The uploaded CSV file is empty.")], []

        header_idx = 0
        for i, row in enumerate(reader[:5]):
            row_str = " ".join([c.lower() for c in row if c])
            if any(k in row_str for k in ["sku", "item code", "product name", "item name"]):
                header_idx = i
                break

        header_row = [c.lower().replace("*", "").strip() for c in reader[header_idx]]
        data_rows = reader[header_idx + 1:]

        return cls._process_tabular_rows(header_row, data_rows, start_row=header_idx + 2)

    @classmethod
    def _process_tabular_rows(cls, headers: List[str], rows: List[Any], start_row: int) -> Tuple[List[Dict[str, Any]], List[RowValidationError], List[RowValidationError]]:
        col_map = {}
        attr_cols = {}

        for idx, h in enumerate(headers):
            matched = False
            for target_field, candidates in HEADER_MAPPINGS.items():
                if any(c == h or h.startswith(c) for c in candidates):
                    col_map[target_field] = idx
                    matched = True
                    break
            if not matched and h:
                # Store extra columns as attributes
                attr_cols[h] = idx

        errors: List[RowValidationError] = []
        warnings: List[RowValidationError] = []
        products: List[Dict[str, Any]] = []
        seen_skus = set()

        for r_offset, row in enumerate(rows):
            curr_row_num = start_row + r_offset
            # Skip completely empty rows
            if not any(row):
                continue

            def get_val(f_name):
                idx = col_map.get(f_name)
                if idx is not None and idx < len(row):
                    return row[idx]
                return None

            raw_sku = clean_str(get_val("sku"))
            name = clean_str(get_val("name"))
            category = clean_str(get_val("category")) or "General"
            brand = clean_str(get_val("brand")) or "Gulmohar Home"
            price_raw = get_val("price")
            mrp_raw = get_val("mrp")
            stock_raw = get_val("stock")
            images_raw = get_val("images")

            # Basic Validation
            if not raw_sku:
                # If name is present, generate a fallback SKU
                if name:
                    raw_sku = "SKU-" + re.sub(r'[^A-Za-z0-9]', '', name[:8]).upper()
                    warnings.append(RowValidationError(
                        row_number=curr_row_num,
                        sku=raw_sku,
                        field="sku",
                        message=f"Missing SKU at row {curr_row_num}; auto-generated '{raw_sku}'.",
                        severity="warning"
                    ))
                else:
                    errors.append(RowValidationError(
                        row_number=curr_row_num,
                        field="sku",
                        message=f"Row {curr_row_num} has no SKU or Product Name. Row skipped.",
                        severity="error"
                    ))
                    continue

            if raw_sku in seen_skus:
                errors.append(RowValidationError(
                    row_number=curr_row_num,
                    sku=raw_sku,
                    field="sku",
                    message=f"Duplicate SKU '{raw_sku}' found at row {curr_row_num}. Each SKU must be unique.",
                    severity="error"
                ))
                continue

            if not name:
                errors.append(RowValidationError(
                    row_number=curr_row_num,
                    sku=raw_sku,
                    field="name",
                    message=f"Product name is required for SKU '{raw_sku}'.",
                    severity="error"
                ))
                continue

            price = clean_num(price_raw, default=0.0)
            if price <= 0:
                warnings.append(RowValidationError(
                    row_number=curr_row_num,
                    sku=raw_sku,
                    field="price",
                    message=f"Selling price is missing or zero for SKU '{raw_sku}'.",
                    severity="warning"
                ))

            mrp = clean_num(mrp_raw, default=0.0) if mrp_raw else (price * 1.2 if price > 0 else 0.0)
            stock = int(clean_num(stock_raw, default=0))

            # Images
            images = []
            if images_raw:
                if isinstance(images_raw, str):
                    images = [img.strip() for img in re.split(r"[,;\n\r]+", images_raw) if img.strip()]
                elif isinstance(images_raw, (int, float)):
                    # Sometimes client imports just image count
                    images = [f"image_{i+1}.jpg" for i in range(int(images_raw))]

            # Also check for other image columns (e.g. Meesho's Secondary Image 2, 3, 4, Image 1, Image 2, Photo URLs)
            extra_img_cols = []
            for attr_name, idx in attr_cols.items():
                an_lower = attr_name.lower()
                if any(k in an_lower for k in ["image", "photo", "img url"]):
                    extra_img_cols.append((an_lower, idx))
            extra_img_cols.sort(key=lambda x: x[0])
            for _, idx in extra_img_cols:
                if idx < len(row):
                    val = clean_str(row[idx])
                    if val and val not in images:
                        images.append(val)

            # Category dynamic attributes
            attributes = {}
            for attr_name, idx in attr_cols.items():
                if idx < len(row):
                    val = clean_str(row[idx])
                    if val:
                        # Clean key title
                        clean_key = attr_name.replace("_", " ").title()
                        attributes[clean_key] = val

            # Check for banned marketing claims in imported name/notes per RUL-4
            banned_keywords = ["free delivery", "free shipping", "best seller", "100% guarantee", "guaranteed quality"]
            for bk in banned_keywords:
                if bk in name.lower():
                    warnings.append(RowValidationError(
                        row_number=curr_row_num,
                        sku=raw_sku,
                        field="name",
                        message=f"Product name contains '{bk}', which is prohibited by Amazon/Flipkart guidelines.",
                        severity="warning"
                    ))

            product_dict = {
                "sku": raw_sku,
                "name": name,
                "category": category,
                "brand": brand,
                "mrp": mrp,
                "price": price,
                "stock": max(0, stock),
                "images": images,
                "image_count": len(images),
                "attributes": attributes,
                "description": attributes.get("Notes") or attributes.get("Occasion / Notes") or ""
            }

            seen_skus.add(raw_sku)
            products.append(product_dict)

        return products, errors, warnings

    @classmethod
    def _parse_tally_xml(cls, content: bytes) -> Tuple[List[Dict[str, Any]], List[RowValidationError], List[RowValidationError]]:
        """Parses Tally XML Stock Item export (<TALLYMESSAGE><STOCKITEM>...)"""
        errors = []
        warnings = []
        products = []
        try:
            root = ET.fromstring(content)
        except Exception as e:
            return [], [RowValidationError(row_number=1, field="xml", message=f"Invalid Tally XML file: {str(e)}")], []

        # Find all STOCKITEM nodes
        stock_items = root.findall(".//STOCKITEM")
        if not stock_items:
            stock_items = root.findall(".//LEDGER")

        for idx, item in enumerate(stock_items, start=1):
            name = item.get("NAME") or ""
            if not name:
                name_elem = item.find("NAME")
                if name_elem is not None and name_elem.text:
                    name = name_elem.text.strip()

            part_no = ""
            part_elem = item.find("PARTNO")
            if part_elem is not None and part_elem.text:
                part_no = part_elem.text.strip()

            sku = part_no if part_no else f"TALLY-{idx:04d}"

            parent = ""
            parent_elem = item.find("PARENT")
            if parent_elem is not None and parent_elem.text:
                parent = parent_elem.text.strip()

            rate = 0.0
            rate_elem = item.find("OPENINGRATE")
            if rate_elem is None:
                rate_elem = item.find("RATE")
            if rate_elem is not None and rate_elem.text:
                rate = clean_num(rate_elem.text)

            closing_qty = 0
            qty_elem = item.find("CLOSINGBALANCE")
            if qty_elem is None:
                qty_elem = item.find("OPENINGBALANCE")
            if qty_elem is not None and qty_elem.text:
                closing_qty = int(clean_num(qty_elem.text))

            if not name:
                continue

            products.append({
                "sku": sku,
                "name": name,
                "category": parent or "General",
                "brand": "Gulmohar Home",
                "mrp": rate * 1.25 if rate > 0 else 0.0,
                "price": rate,
                "stock": max(0, closing_qty),
                "images": [],
                "image_count": 0,
                "attributes": {
                    "Tally Group": parent,
                    "Import Source": "Tally XML"
                },
                "description": f"Imported from Tally Stock Item: {name}"
            })

        return products, errors, warnings
