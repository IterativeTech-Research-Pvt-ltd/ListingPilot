"""
Meesho Supplier Panel Adapter & Agnostic Template Engine (MSH-1, MSH-2)
Dynamically scans and populates official Meesho Supplier Panel Excel flat files (.xlsx)
from `docs/meesho/templates` (or configured templates directory).

Agnostic Design:
  - Works with N number of official templates dropped into the templates directory.
  - Dynamically extracts column names from Row 3 (the official Meesho header definition).
  - Preserves 100% of the original workbook structure, data validation dropdowns ('Validation Sheet'),
    instructions, and example sheets.
  - Master templates are strictly read-only; all operations run on fresh in-memory copies.
  - Automatically groups multi-category batches into clean individual .xlsx files or a .zip archive.
"""
import io
import os
import re
import glob
import json
import zipfile
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
import openpyxl.utils
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from app.core.config import settings
from app.models.product import Product
from app.models.draft import ListingDraft

ROOT_DIR = Path(__file__).resolve().parents[3]
PRIMARY_TEMPLATES_DIR = ROOT_DIR / "docs" / "meesho" / "templates"
SECONDARY_TEMPLATES_DIR = ROOT_DIR / "docs" / "templates"
MEESHO_CATEGORIES_FILE = ROOT_DIR / "docs" / "meesho" / "categories" / "meeshoCategories.json"

# Dropdown columns where a partial match would change meaning (identifiers, and colours, where
# "Indigo and white" must not become "White"): only exact or numeric matches are accepted
EXACT_MATCH_COLUMNS = ("hsn", "gst", "country", "group id", "color", "colour")

# Template columns whose name clashes with an attribute that means something else: the Bedsheets
# "Size" dropdown (Double Queen, Single...) is read from "Bed Size", since "Size" holds the measurement
SELLER_ATTRIBUTE_FOR_COLUMN = {("bedsheets", "size"): "Bed Size"}

# Meesho's catalogue QC flags these words in descriptions (seen in processed upload files)
MEESHO_FLAGGED_WORDS = ("care", "comfort", "colors")


class MeeshoExportIncomplete(Exception):
    """Raised instead of producing a file Meesho would reject or that would carry made-up values."""

    def __init__(self, problems: List[Dict[str, str]]):
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s) block the Meesho export")


def _attr(attrs: Dict[str, Any], *names: str) -> Optional[str]:
    """First non-empty attribute among names, matched case-insensitively."""
    lowered = {str(k).strip().lower(): v for k, v in (attrs or {}).items()}
    for name in names:
        v = lowered.get(name.lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _inch_dims(text: Optional[str]) -> Optional[Tuple[float, float]]:
    """(longer, shorter) side from the first 'A x B in' in text, e.g. '90 x 100 in (double)'."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:in\b|inch|\")", text or "", flags=re.IGNORECASE)
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    return max(a, b), min(a, b)


def _grams(text: Optional[str]) -> Optional[int]:
    """Weight in grams from '500', '350 g (set)' or '1.2 kg'; None when no unit-bearing number."""
    if not text:
        return None
    if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", text):
        return int(round(float(text)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kgs|g|gm|gms|grams?)\b", text, flags=re.IGNORECASE)
    if not m:
        return None
    qty = float(m.group(1))
    return int(round(qty * 1000 if m.group(2).lower().startswith("kg") else qty))


def _fmt_num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _dimension_option(size_text: Optional[str], variation: Optional[str], options: List[str]) -> Optional[str]:
    """
    The one 'A*B-(Label)' option (e.g. '90*100-(Double)') with the same two sides as the stated
    size, narrowed by the row's Variation when several share those sides. None unless exactly one fits.
    """
    dims = _inch_dims(size_text)
    if not dims:
        return None
    fits = []
    for opt in options:
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*\*\s*(\d+(?:\.\d+)?)\s*-\s*\((.+)\)\s*", opt)
        if m and sorted((float(m.group(1)), float(m.group(2)))) == sorted(dims):
            fits.append((opt, m.group(3).strip().lower()))
    if len(fits) > 1 and variation:
        fits = [f for f in fits if f[1] == variation.strip().lower()]
    return fits[0][0] if len(fits) == 1 else None


class MeeshoAdapter:
    """Adapter and dynamic engine for Meesho Supplier Panel catalog generation."""

    _cached_registry: Optional[Dict[str, Dict[str, Any]]] = None
    _cached_categories: Optional[List[Dict[str, str]]] = None

    @classmethod
    def get_templates_dir(cls) -> Path:
        """Returns the active templates directory containing official Meesho .xlsx templates."""
        if PRIMARY_TEMPLATES_DIR.exists():
            return PRIMARY_TEMPLATES_DIR
        elif SECONDARY_TEMPLATES_DIR.exists():
            return SECONDARY_TEMPLATES_DIR
        return PRIMARY_TEMPLATES_DIR

    @classmethod
    def scan_available_templates(cls, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Agnostically scans the templates directory for any number of official Meesho .xlsx files.
        Extracts category names, active data sheet ('<Category>-Fill this'), hierarchy, and columns.
        """
        if cls._cached_registry is not None and not force_refresh:
            return cls._cached_registry

        registry = {}
        tmpl_dir = cls.get_templates_dir()
        if not tmpl_dir.exists():
            cls._cached_registry = registry
            return registry

        xlsx_files = sorted(glob.glob(str(tmpl_dir / "*.xlsx")))
        for fpath in xlsx_files:
            fname = os.path.basename(fpath)
            try:
                # Load with openpyxl in read-only / metadata inspection mode
                wb = openpyxl.load_workbook(fpath, data_only=True)
                fill_sheet = next((s for s in wb.sheetnames if "-Fill this" in s), None)
                if not fill_sheet and len(wb.sheetnames) > 1:
                    fill_sheet = wb.sheetnames[1]

                if not fill_sheet:
                    continue

                sh = wb[fill_sheet]
                cat_raw = fill_sheet.replace("-Fill this", "").strip()
                cat_norm = cls._normalize_cat_key(cat_raw)
                hierarchy = str(sh.cell(1, 1).value or "")

                # Extract column definitions from Row 3 and field types from Row 2
                col_map = {}
                compulsory_cols = set()
                for col_idx in range(1, sh.max_column + 1):
                    r2_val = str(sh.cell(2, col_idx).value or "").strip()
                    if "* Compulsory" in r2_val or "Compulsory" in r2_val:
                        compulsory_cols.add(col_idx)
                    r3_val = str(sh.cell(3, col_idx).value or "").strip()
                    col_title = r3_val.split("\n")[0].strip() if r3_val else f"Col_{col_idx}"
                    col_map[col_idx] = col_title

                # Extract dropdown options from Validation Sheet (Row 3 downwards)
                dropdowns = {}
                if "Validation Sheet" in wb.sheetnames:
                    ws_val = wb["Validation Sheet"]
                    for col_idx in range(1, min(sh.max_column + 1, ws_val.max_column + 1)):
                        opts = []
                        for r in range(3, ws_val.max_row + 1):
                            v = ws_val.cell(r, col_idx).value
                            if v is not None and str(v).strip():
                                opts.append(str(v).strip())
                        if opts:
                            dropdowns[col_idx] = opts

                template_info = {
                    "category": cat_raw,
                    "normalized_category": cat_norm,
                    "filename": fname,
                    "filepath": fpath,
                    "sheet_name": fill_sheet,
                    "all_sheets": wb.sheetnames,
                    "hierarchy": hierarchy,
                    "total_columns": sh.max_column,
                    "columns": col_map,
                    "compulsory_columns": list(compulsory_cols),
                    "dropdowns": dropdowns,
                }

                registry[cat_norm] = template_info
                # Also store by exact category name
                registry[cat_raw.lower()] = template_info

            except Exception as e:
                print(f"[MeeshoAdapter] Notice: Could not index template {fname}: {e}")

        cls._cached_registry = registry
        return registry

    @classmethod
    def get_available_templates(cls) -> List[Dict[str, Any]]:
        """Returns clean list of registered template descriptors for frontend/API."""
        reg = cls.scan_available_templates()
        seen = set()
        out = []
        for v in reg.values():
            if v["filename"] not in seen:
                seen.add(v["filename"])
                out.append({
                    "category": v["category"],
                    "filename": v["filename"],
                    "sheet_name": v["sheet_name"],
                    "total_columns": v["total_columns"],
                    "hierarchy": v["hierarchy"],
                    "dropdown_columns_count": len(v.get("dropdowns", {})),
                    "filepath": v["filepath"],
                    "columns": v["columns"],
                    "compulsory_columns": v["compulsory_columns"],
                    "dropdowns": v["dropdowns"],
                })
        return out

    @classmethod
    def load_category_taxonomy(cls) -> List[Dict[str, str]]:
        """Loads and flattens all leaf categories from meeshoCategories.json."""
        if cls._cached_categories is not None:
            return cls._cached_categories

        leafs: List[Dict[str, str]] = []
        if MEESHO_CATEGORIES_FILE.exists():
            try:
                with open(MEESHO_CATEGORIES_FILE, "r", encoding="utf-8") as f:
                    tree = json.load(f)

                def walk(nodes: List[Dict[str, Any]], current_path: str):
                    for node in nodes:
                        name = node.get("name", "").strip()
                        p = f"{current_path}/{name}" if current_path else name
                        children = node.get("children", [])
                        if not children:
                            leafs.append({"name": name, "path": p})
                        else:
                            walk(children, p)

                walk(tree, "")
            except Exception as e:
                print(f"[MeeshoAdapter] Warning: Could not parse meeshoCategories.json: {e}")

        cls._cached_categories = leafs
        return leafs

    @classmethod
    def get_categories(cls, search: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Searches the 3,787 official Meesho leaf categories, annotating each with template availability.
        """
        all_leafs = cls.load_category_taxonomy()
        q = (search or "").strip().lower()

        results = []
        for item in all_leafs:
            if not q or q in item["name"].lower() or q in item["path"].lower():
                tmpl = cls.find_template(item["name"]) or cls.find_template(item["path"])
                results.append({
                    "name": item["name"],
                    "path": item["path"],
                    "template_available": tmpl is not None,
                    "template_filename": tmpl["filename"] if tmpl else None,
                    "template_category": tmpl["category"] if tmpl else None,
                })
                if len(results) >= limit:
                    break

        return results

    @classmethod
    def find_template(cls, category_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Matches an item's category name against registered templates using:
          1. Exact (normalized) match
          2. A taxonomy path equal to the template's own path
          3. The category's head noun ("Double Bedsheets" -> Bedsheets, "Brother & Sister T-Shirts" -> Tshirts)
          4. Head-noun synonyms ("Tees" -> Tshirts)
        Whole words only: "Steel bottles", "Settees" and "Sweatshirts" match no template.
        """
        if not category_name:
            return None

        reg = cls.scan_available_templates()
        norm_key = cls._normalize_cat_key(category_name)

        # 1. Direct normalized match
        if norm_key in reg:
            return reg[norm_key]

        # 2. A full taxonomy path (e.g. from meeshoCategories.json), compared with the template's own path
        if "/" in category_name:
            path = category_name.strip().lower()
            for tmpl in reg.values():
                m = re.search(r"\(([^)]*)\)", tmpl.get("hierarchy") or "")
                if m and m.group(1).strip().lower() == path:
                    return tmpl
            category_name = category_name.rsplit("/", 1)[-1]
            norm_key = cls._normalize_cat_key(category_name)
            if norm_key in reg:
                return reg[norm_key]

        # 3. Head noun of each part, longest template first so 'tshirts' wins over 'shirts'
        heads = cls._head_keys(category_name)
        sorted_tmpls = sorted(
            reg.values(),
            key=lambda t: len(t.get("normalized_category", "")),
            reverse=True
        )
        for tmpl in sorted_tmpls:
            if tmpl["normalized_category"] in heads:
                return tmpl

        # 4. Head-noun synonyms (normalized head -> template key). Not 'bedding' or 'duvet': pet
        # bedding or a duvet in the Bedsheets template fails Meesho QC, like footwear in Sneakers
        synonyms = {"tee": "tshirts"}
        for syn, target in synonyms.items():
            if syn in heads and target in reg:
                return reg[target]

        return None

    @classmethod
    def _head_keys(cls, name: str) -> set:
        """
        Normalized head nouns of each '&' / ',' separated part, with the one or two words before
        them joined on, so 'T-Shirts' and 'Bed Sheets' give 'tshirt' and 'bedsheet'.
        """
        keys = set()
        for part in re.split(r"[&,;+/]|\band\b", (name or "").lower()):
            words = re.findall(r"[a-z0-9]+", part)
            for n in (1, 2, 3):
                if len(words) >= n:
                    keys.add(cls._normalize_cat_key("".join(words[-n:])))
        return keys

    @classmethod
    def _normalize_cat_key(cls, name: str) -> str:
        """Strips symbols, spaces, and trailing 's' for flexible matching."""
        s = re.sub(r"[^a-zA-Z0-9]", "", (name or "").lower())
        return s.rstrip("s") if len(s) > 3 and s.endswith("s") else s

    @classmethod
    def _match_dropdown_option(cls, val: Any, options: List[str], col_name: str = "") -> Optional[str]:
        """
        Maps a product value to one of the template's dropdown options, written exactly as the
        template spells it. Only high-confidence matches are returned; anything else is None so
        the caller can flag it for review instead of guessing:
          1. exact (case-insensitive) match
          2. same number ("5.0" -> "5") or number with a unit ("180 TC" -> "180", "5%" -> "5")
          3. exactly one option named as a whole word/phrase in the value
             ("100% cotton" -> "Cotton", "90 x 100 in (double)" -> "Double")
        Step 3 is skipped for Brand and EXACT_MATCH_COLUMNS, which must match exactly.
        """
        if not options:
            return val
        if val is None or not str(val).strip():
            return None

        opt_map = {opt.strip().lower(): opt for opt in options if opt and opt.strip()}
        raw_str = str(val).strip()
        raw_lower = raw_str.lower()

        if raw_lower in opt_map:
            return opt_map[raw_lower]

        num_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[a-z%]*", raw_lower)
        if num_match:
            fval = float(num_match.group(1))
            for opt_l, opt_orig in opt_map.items():
                try:
                    if float(opt_l) == fval:
                        return opt_orig
                except ValueError:
                    pass

        cn = col_name.strip().lower()
        if cn == "brand" or any(k in cn for k in EXACT_MATCH_COLUMNS):
            return None

        # Longest options first, consuming matched text, so "Navy Blue" wins over "Blue"
        remaining = raw_lower
        found = []
        for opt_l in sorted(opt_map, key=len, reverse=True):
            if re.fullmatch(r"[\d.]+", opt_l):
                continue
            pattern = rf"(?<![a-z0-9]){re.escape(opt_l)}(?![a-z0-9])"
            if re.search(pattern, remaining):
                found.append(opt_map[opt_l])
                remaining = re.sub(pattern, " ", remaining)
        return found[0] if len(found) == 1 else None

    @classmethod
    def validate_credentials(cls) -> Dict[str, Any]:
        """Validate Meesho integration status (MSH-1)."""
        available = cls.get_available_templates()
        tmpl_names = [t["category"] for t in available]
        return {
            "marketplace": "meesho",
            "configured": True,
            "mode": "supplier_panel_files",
            "template_format": "official_multisheet_flat_file",
            "active_templates_count": len(available),
            "available_categories": tmpl_names,
            "message": f"Meesho Agnostic Template Engine ready ({len(available)} category template(s) loaded).",
            "instructions": "Download the generated .xlsx file and upload directly at supplier.meesho.com ➔ Catalog Upload ➔ Add Catalog in Bulk ➔ Upload Completed Template."
        }

    @classmethod
    def _row_inputs(cls, item: Dict[str, Any]) -> Dict[str, Any]:
        """Product and draft data for one sheet row. Nothing is defaulted or estimated here."""
        product = item.get("product")
        draft = item.get("draft") or {}

        def pick(attr: str, default: Any = None) -> Any:
            return getattr(product, attr, default) if product else item.get(attr, default)

        def draft_field(key: str) -> Any:
            return draft.get(key) if isinstance(draft, dict) else getattr(draft, key, None)

        name = pick("name") or ""
        title = re.sub(r"<[^>]+>", "", draft_field("title") or name).strip()[:95]

        bullets = [re.sub(r"<[^>]+>", "", str(b)).strip() for b in (draft_field("bullets") or [])]
        desc = re.sub(r"<[^>]+>", "", draft_field("description") or "").strip()
        if bullets:
            full_desc = f"{desc}\n\nKey Features:\n" + "\n".join(f"• {b}" for b in bullets)
        else:
            full_desc = desc or (pick("description") or "").strip() or None

        price = float(pick("price") or 0)
        mrp = pick("mrp")
        stock = pick("stock")
        attrs = pick("attributes") or {}
        return {
            "sku": pick("sku") or "",
            "name": name,
            "title": title,
            "price": price if price > 0 else None,
            "mrp": float(mrp) if mrp else None,
            "stock": int(stock) if stock is not None else None,
            "brand": pick("brand") or None,
            "attrs": attrs,
            "images": pick("images") or [],
            "description": full_desc,
            "style_id": pick("style_id") or _attr(attrs, "Style Code", "Style ID") or pick("sku") or "",
        }

    @classmethod
    def _seller_attribute(cls, category: str, col_name: str) -> str:
        """Attribute a column is read from: the column's own name unless that name means something else."""
        return SELLER_ATTRIBUTE_FOR_COLUMN.get((category.strip().lower(), col_name.strip().lower()), col_name)

    @classmethod
    def _template_value(cls, cn: str, col_name: str, row: Dict[str, Any], category: str) -> Any:
        """
        Value for one official-template column, taken only from the product's own data.
        Returns None when the data doesn't say; compulsory gaps are reported by the caller.
        """
        if "error status" in cn or "error message" in cn:
            return None

        attrs = row["attrs"]
        # An attribute named exactly like the column wins, so sellers can set Meesho values directly
        seller_attr = cls._seller_attribute(category, col_name)
        direct = _attr(attrs, seller_attr)
        if "net weight" in cn:
            return _grams(direct or _attr(attrs, "Net Weight (gms)", "Net Weight", "Weight"))
        if direct is not None or seller_attr != col_name:
            return direct

        size_text = _attr(attrs, "Size", "Dimensions")
        included = _attr(attrs, "Included Components", "Included", "Sales Package", "Package Contents", "In The Box")
        pillow_text = included[included.lower().index("pillow"):] if included and "pillow" in included.lower() else None

        if "product name" in cn:
            return row["title"]
        if "variation" in cn:
            return _attr(attrs, "Size", "Variation")
        if "meesho price" in cn:
            return row["price"]
        if "wrong/defective" in cn:
            return _attr(attrs, "Wrong/Defective Return Discount", "Wrong/Defective Discount")
        if cn == "mrp":
            return row["mrp"]
        if "gst" in cn:
            return _attr(attrs, "GST %", "GST Rate", "GST")
        if "hsn" in cn:
            return _attr(attrs, "HSN ID", "HSN Code", "HSN")
        if "inventory" in cn:
            return row["stock"]
        img = re.match(r"image (\d)", cn)
        if img:
            n = int(img.group(1))
            return row["images"][n - 1] if len(row["images"]) >= n else None
        if "color" in cn or "colour" in cn:
            return _attr(attrs, "Color", "Colour")
        # Exact columns only: 'Sole Material' is not the upper's material
        if cn in ("fabric", "material"):
            return _attr(attrs, "Fabric", "Material")
        if "generic name" in cn:
            return _attr(attrs, "Generic Name") or category
        if "included components" in cn:
            return included
        if "net quantity" in cn:
            return _attr(attrs, "Net Quantity", "Net Quantity (N)")
        if "pillow length" in cn or "pillow width" in cn:
            dims = _inch_dims(pillow_text)
            return _fmt_num(dims[0] if "length" in cn else dims[1]) if dims else None
        if "no. of pillow" in cn:
            m = re.search(r"(\d+)\s*pillow", included or "", flags=re.IGNORECASE)
            return m.group(1) if m else None
        if "bedsheet length" in cn or "bedsheet width" in cn:
            dims = _inch_dims(size_text)
            return _fmt_num(dims[0] if "length" in cn else dims[1]) if dims else None
        if ("length" in cn or "width" in cn) and "cm" in cn:
            dims = _inch_dims(size_text)
            return round((dims[0] if "length" in cn else dims[1]) * 2.54) if dims else None
        # Newer templates: the stated inch size as-is, with its unit in a separate column
        if cn in ("product length", "product width"):
            dims = _inch_dims(size_text)
            if not dims:
                return None
            side = dims[0] if "length" in cn else dims[1]
            return int(side) if side.is_integer() else side
        if cn == "product dimension unit":
            return "inch" if _inch_dims(size_text) else None
        if cn == "dimensions (inches)":
            return size_text
        # Exact columns only: 'Weave Pattern' (twill, oxford) is not the print pattern
        if cn in ("pattern", "print or pattern type"):
            return _attr(attrs, "Pattern", "Print")
        if "product id" in cn or "style id" in cn:
            return row["style_id"]
        if "sku id" in cn or "seller sku" in cn:
            return row["sku"]
        if "brand name" in cn or cn == "brand":
            return row["brand"]
        if "product description" in cn:
            return row["description"]
        if "group id" in cn:
            return _attr(attrs, "Group ID", "Group")
        return None

    @classmethod
    def _duplicate_name_problems(cls, name_rows: Dict[str, List[Dict[str, Any]]], category: str) -> List[Dict[str, Any]]:
        """
        Meesho treats rows sharing a Product Name as sizes of one product, then rejects them when
        their attributes or images differ. Rows may share a name only as distinct sizes of one Style ID.
        """
        problems = []
        for rows in name_rows.values():
            if len(rows) < 2:
                continue
            sizes = [_attr(r["attrs"], "Size", "Variation") for r in rows]
            same_style = len({r["style_id"] for r in rows}) == 1
            if same_style and len(set(sizes)) == len(sizes):
                continue
            for r in rows:
                others = ", ".join(o["sku"] for o in rows if o is not r)
                problems.append({
                    "sku": r["sku"], "category": category, "field": "Product Name",
                    "reason": f"same Product Name as {others}; Meesho would merge them as sizes of one product",
                    "blocking": True,
                })
        return problems

    @classmethod
    def populate_template(
        cls,
        template_info: Dict[str, Any],
        products_with_drafts: List[Dict[str, Any]]
    ) -> io.BytesIO:
        """
        Populates a non-destructive in-memory copy of an official Meesho template.
        Reads column mapping dynamically from Row 3 to adapt to ANY official template.
        Preserves all other sheets (Instructions, Example Sheet, Validation Sheet, Return Reasons).
        """
        if "filepath" not in template_info or "columns" not in template_info:
            full_tmpl = cls.find_template(template_info.get("category"))
            if full_tmpl:
                template_info = full_tmpl
            else:
                raise ValueError(f"Template descriptor missing 'filepath' and cannot find template for category: {template_info.get('category')}")

        fpath = template_info["filepath"]
        with open(fpath, "rb") as f:
            master_bytes = f.read()

        # Load in-memory copy preserving all formatting, formulas, and validations
        wb = openpyxl.load_workbook(io.BytesIO(master_bytes))
        fill_sheet_name = template_info["sheet_name"]
        ws = wb[fill_sheet_name]

        col_map = template_info["columns"]
        dropdowns = template_info.get("dropdowns", {})
        compulsory_cols = set(template_info.get("compulsory_columns", []))
        font_data = Font(name="Arial", size=10)
        border_thin = Border(
            left=Side(style="thin", color="E0E0E0"),
            right=Side(style="thin", color="E0E0E0"),
            top=Side(style="thin", color="E0E0E0"),
            bottom=Side(style="thin", color="E0E0E0"),
        )

        category = template_info.get("category", "")
        problems: List[Dict[str, Any]] = []
        name_rows: Dict[str, List[Dict[str, Any]]] = {}

        # Ingest each product row starting at Row 5
        for idx, item in enumerate(products_with_drafts):
            target_row = 5 + idx
            row = cls._row_inputs(item)
            written: Dict[str, Any] = {}

            for col_idx, col_name in col_map.items():
                cell = ws.cell(row=target_row, column=col_idx)
                cell.font = font_data
                cell.border = border_thin
                cell.alignment = Alignment(vertical="center")

                cn = col_name.strip().lower()
                val = cls._template_value(cn, col_name, row, category)

                # Write dropdown columns only as an option the template itself lists
                if col_idx in dropdowns and val is not None and str(val).strip():
                    matched = cls._match_dropdown_option(val, dropdowns[col_idx], col_name=col_name)
                    if matched is None and cn == "dimensions (inches)":
                        matched = _dimension_option(str(val), written.get("Variation"), dropdowns[col_idx])
                    if matched is None:
                        problems.append({
                            "sku": row["sku"], "category": category, "field": col_name,
                            "reason": f"'{val}' is not one of the template's options; add a "
                                      f"'{cls._seller_attribute(category, col_name)}' attribute set to one of them",
                            "blocking": col_idx in compulsory_cols,
                        })
                    val = matched

                if col_idx in compulsory_cols and (val is None or not str(val).strip()):
                    if not any(pr["sku"] == row["sku"] and pr["field"] == col_name for pr in problems):
                        problems.append({
                            "sku": row["sku"], "category": category, "field": col_name,
                            "reason": "compulsory and missing from the product's data",
                            "blocking": True,
                        })

                cell.value = val
                written[col_name] = val
            ws.row_dimensions[target_row].height = 22
            name_rows.setdefault(row["title"].lower(), []).append(row)

        problems.extend(cls._duplicate_name_problems(name_rows, category))
        if any(pr["blocking"] for pr in problems):
            raise MeeshoExportIncomplete(problems)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    @classmethod
    def generate_batch_export(
        cls,
        products_with_drafts: List[Dict[str, Any]],
        category_filter: Optional[str] = None,
        force_zip: bool = False
    ) -> Tuple[io.BytesIO, str, str]:
        """
        Groups items by category and fills each category's official template.
          - One category: returns (xlsx_buf, xlsx media type, filename)
          - Several categories: returns a zip with one .xlsx per category
        force_zip is accepted for API compatibility; several categories are always zipped.
        """
        # If category filter provided, restrict items
        if category_filter and category_filter != "All":
            filtered = []
            for item in products_with_drafts:
                p = item.get("product")
                cat = getattr(p, "category", None) or item.get("category")
                if cat and cls._normalize_cat_key(cat) == cls._normalize_cat_key(category_filter):
                    filtered.append(item)
            products_with_drafts = filtered
        if not products_with_drafts:
            raise ValueError(f"No products in category '{category_filter}' to export.")

        # Group items by category
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in products_with_drafts:
            product = item.get("product")
            cat = (
                category_filter
                or getattr(product, "category", None)
                or item.get("category")
                or "General"
            )
            grouped.setdefault(cat, []).append(item)

        generated_files: List[Tuple[str, io.BytesIO]] = []
        problems: List[Dict[str, Any]] = []

        for cat_name, cat_items in grouped.items():
            tmpl = cls.find_template(cat_name)
            if not tmpl:
                problems.extend(cls._missing_template_problems(cat_name, cat_items))
                continue
            try:
                buf = cls.populate_template(tmpl, cat_items)
            except MeeshoExportIncomplete as e:
                # Keep going so one response lists every category's problems
                problems.extend(e.problems)
                continue

            safe_cat = re.sub(r"[^a-zA-Z0-9_-]", "_", cat_name)
            file_name = f"ListingPilot_Meesho_{safe_cat}.xlsx"
            generated_files.append((file_name, buf))

        if problems:
            raise MeeshoExportIncomplete(problems)

        # One category: the .xlsx itself; several: always a zip, so no category's file is dropped
        if len(generated_files) == 1:
            file_name, buf = generated_files[0]
            return (
                buf,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                file_name,
            )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_name, file_buf in generated_files:
                zf.writestr(file_name, file_buf.getvalue())
        zip_buf.seek(0)

        date_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        return (
            zip_buf,
            "application/zip",
            f"ListingPilot_Meesho_Batch_{date_stamp}.zip",
        )

    @classmethod
    def build_fill_in_sheet(cls, products_with_drafts: List[Dict[str, Any]]) -> Optional[io.BytesIO]:
        """
        Workbook listing, per SKU, the Meesho fields its data is missing, laid out for the catalogue
        import (column headers are the template's own names, which the export reads back as attributes).
        Returns None when every product would export cleanly.
        """
        problems: List[Dict[str, Any]] = []
        options: Dict[str, List[str]] = {}
        field_order: List[str] = []
        attr_names: Dict[str, str] = {}
        for cat_name, cat_items in cls._group_by_category(products_with_drafts).items():
            tmpl = cls.find_template(cat_name)
            if tmpl:
                for col_idx, col_name in tmpl["columns"].items():
                    if col_name not in field_order:
                        field_order.append(col_name)
                    attr_names.setdefault(col_name, cls._seller_attribute(cat_name, col_name))
                    if col_idx in tmpl.get("dropdowns", {}):
                        options.setdefault(col_name, tmpl["dropdowns"][col_idx])
            if not tmpl:
                problems.extend(cls._missing_template_problems(cat_name, cat_items))
                continue
            try:
                cls.populate_template(tmpl, cat_items)
            except MeeshoExportIncomplete as e:
                problems.extend(e.problems)
        blocking = [p for p in problems if p["blocking"]]
        if not blocking:
            return None

        image_fields = ["Image 1 (Front)", "Image 2", "Image 3", "Image 4"]
        # Product Name problems are fixed by regenerating the draft, not by filling a cell
        fields = [f for f in field_order if any(p["field"] == f for p in blocking)
                  and f != "Product Name" and not f.lower().startswith("image")]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Fill in"
        # Headers are the attribute names the export reads back, e.g. "Bed Size" for Bedsheets' Size
        headers = ["SKU", "Product Name", "Category", *[attr_names.get(f, f) for f in fields], *image_fields]
        ws.append(headers)
        bold = Font(name="Arial", size=10, bold=True)
        need_fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
        for cell in ws[1]:
            cell.font = bold

        needs = {(p["sku"], p["field"]) for p in blocking}
        skus_needing = {sku for sku, _ in needs}
        for item in products_with_drafts:
            row = cls._row_inputs(item)
            if row["sku"] not in skus_needing:
                continue
            category = getattr(item.get("product"), "category", None) or item.get("category")
            images = row["images"]
            ws.append([row["sku"], row["name"], category, *[None] * len(fields),
                       *[images[i] if len(images) > i else None for i in range(4)]])
            r = ws.max_row
            for offset, f in enumerate([*fields, *image_fields]):
                if (row["sku"], f) in needs:
                    ws.cell(row=r, column=4 + offset).fill = need_fill

        # Dropdowns with the template's exact option spellings
        ws_opt = wb.create_sheet("Allowed values")
        opt_col = 0
        for offset, f in enumerate(fields):
            if f not in options:
                continue
            opt_col += 1
            letter = openpyxl.utils.get_column_letter(opt_col)
            ws_opt.cell(row=1, column=opt_col, value=attr_names.get(f, f)).font = bold
            for i, opt in enumerate(options[f], start=2):
                ws_opt.cell(row=i, column=opt_col, value=opt)
            dv = DataValidation(type="list", formula1=f"='Allowed values'!${letter}$2:${letter}${len(options[f]) + 1}",
                                allow_blank=True)
            ws.add_data_validation(dv)
            target = openpyxl.utils.get_column_letter(4 + offset)
            dv.add(f"{target}2:{target}{max(ws.max_row, 2)}")

        ws_why = wb.create_sheet("What's wrong")
        ws_why.append(["SKU", "Category", "Field", "Problem"])
        for cell in ws_why[1]:
            cell.font = bold
        for p in problems:
            ws_why.append([p["sku"], p["category"], p["field"], p["reason"]])

        ws_how = wb.create_sheet("How to use")
        for line in [
            "1. Fill the highlighted cells on 'Fill in'. Dropdown cells take only Meesho's own values.",
            "2. Replace the image links with links from Meesho's supplier panel image uploader (stock photos fail QC).",
            "3. Import this file in ListingPilot's Catalogue tab. Values are saved to each SKU; nothing else changes.",
            "4. Export the Meesho sheet again. 'What's wrong' lists every problem found, including non-blocking ones.",
        ]:
            ws_how.append([line])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    @classmethod
    def _group_by_category(cls, products_with_drafts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in products_with_drafts:
            cat = getattr(item.get("product"), "category", None) or item.get("category") or "General"
            grouped.setdefault(cat, []).append(item)
        return grouped

    @classmethod
    def generate_bulk_upload_file(
        cls,
        category: str,
        products_with_drafts: List[Dict[str, Any]]
    ) -> io.BytesIO:
        """Fills the official template for one category; there is no substitute layout."""
        tmpl = cls.find_template(category)
        if not tmpl:
            raise MeeshoExportIncomplete(cls._missing_template_problems(category, products_with_drafts))
        return cls.populate_template(tmpl, products_with_drafts)

    @classmethod
    def _missing_template_problems(cls, category: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Meesho only accepts its own category template, so a category without one can't be exported."""
        return [{
            "sku": cls._row_inputs(item)["sku"], "category": category, "field": "Template",
            "reason": f"no official Meesho template for '{category}'; download it from the supplier panel "
                      f"(Catalog Upload > Bulk) into docs/meesho/templates",
            "blocking": True,
        } for item in items]
