"""
Meesho Supplier Panel Adapter & Agnostic Template Engine (MSH-1, MSH-2)
Dynamically scans and populates official Meesho Supplier Panel Excel flat files (.xlsx)
from `docs/meesho/Meesho Templates/<category path>/`.

Agnostic Design:
  - Works with N number of official templates, one per Meesho category folder; only the ones an export uses are opened.
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
from app.services.settings_service import SettingsService, SELLER_DETAIL_FIELDS
from app.services.marketplace_limits import title_limit
from app.models.product import Product
from app.models.draft import ListingDraft

ROOT_DIR = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = ROOT_DIR / "docs" / "meesho" / "Meesho Templates"
MEESHO_CATEGORIES_FILE = ROOT_DIR / "docs" / "meesho" / "categories" / "meeshoCategories.json"

# Dropdown columns where a partial match would change meaning (identifiers, and colours, where
# "Indigo and white" must not become "White"): only exact or numeric matches are accepted
EXACT_MATCH_COLUMNS = ("hsn", "gst", "country", "group id", "color", "colour")

# Template columns whose name clashes with an attribute that means something else: the Bedsheets
# "Size" dropdown (Double Queen, Single...) is read from "Bed Size", since "Size" holds the measurement
SELLER_ATTRIBUTE_FOR_COLUMN = {("bedsheets", "size"): "Bed Size"}

# Product attribute holding the seller's Meesho category for the product: Meesho's template id
# (as saved by the category picker) or its breadcrumb (as typed in an imported sheet)
MEESHO_CATEGORY_ATTR = "Meesho Category"
# Joins category levels the way they're shown and typed; no Meesho category name contains '>'
BREADCRUMB_SEP = " > "

# Top-level Meesho sections that serve one audience, and the words in a product name that state one;
# a template found by name alone is not used for a product named for another audience
AUDIENCE_SECTIONS = {
    "men": ("men fashion", "men's grooming", "mens personal care & grooming"),
    "women": ("women fashion", "women"),
    "kids": ("kids", "kids & toys"),
}
AUDIENCE_WORDS = {
    "men": r"\b(men|mens|men's|male)\b",
    "women": r"\b(women|womens|women's|ladies|female)\b",
    "kids": r"\b(kids?|kid's|boys?|boy's|girls?|girl's|baby|toddler|infant)\b",
}

MEESHO_TITLE_LIMIT = title_limit("meesho")
# What the template says to keep out of Product Name ("weight, dimension, price") and other portals'
# names. Bare units that are also common words or model names ("2 in 1", "5G", "3M") aren't matched.
PRODUCT_NAME_RULES = [
    ("a weight", r"\b\d+(?:\.\d+)?\s*(?:kg|kgs|gm|gms|grams?)\b"),
    ("a dimension", r"\b\d+(?:\.\d+)?\s*[x×*]\s*\d+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\s*(?:cm|mm|inch|inches|ft|feet|foot|meters?|metres?)\b|\b\d+(?:\.\d+)?\s*\""),
    ("a price", r"₹|\brs\.?\s*\d|\binr\s*\d|\b\d+\s*(?:rs|rupees)\b"),
    ("another marketplace's name", r"\b(?:amazon|flipkart|myntra|ajio|snapdeal|nykaa|jiomart|tata\s*cliq|shopsy|glowroad)\b"),
]
# Image links Meesho can't use: the template asks for links from its own Images Bulk Upload and
# refuses Google Drive; stock photos and our own storage or machine aren't the seller's Meesho images
UNUSABLE_IMAGE_LINKS = [
    ("a Google Drive", r"\b(?:drive|docs)\.google\.com\b"),
    ("a stock-photo", r"\b(?:unsplash\.com|pexels\.com|pixabay\.com|shutterstock\.com|istockphoto\.com)\b"),
    ("a local", r"://(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|192\.168\.)"),
    ("a ListingPilot storage", r"\.supabase\.co/storage/"),
]

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


def _number(value: Any) -> Optional[float]:
    """A written cell's number (499, 499.0, '499', '₹ 499'); None when it holds no number."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"\s*(?:₹|rs\.?|inr)?\s*(-?\d+(?:\.\d+)?)\s*", str(value or ""), flags=re.IGNORECASE)
    return float(m.group(1)) if m else None


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

    _cached_index: Optional[Dict[str, Any]] = None
    _loaded_templates: Dict[str, Dict[str, Any]] = {}
    _cached_categories: Optional[List[Dict[str, str]]] = None

    @classmethod
    def get_templates_dir(cls) -> Path:
        """The folder holding the official Meesho .xlsx templates, one sub-folder per category path."""
        return TEMPLATES_DIR

    @classmethod
    def template_index(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Every official template, found from its folder: '<dir>/Home & Kitchen/.../Bedsheets/Bedsheets-12776-...xlsx'
        is the template for that category, with Meesho's template id 12776. No workbook is opened
        here (there are thousands); _load_template reads the one an export uses.
        Each entry carries the category's real names from meeshoCategories.json as `segments` and
        `breadcrumb` ('Home & Kitchen > ... > Bedsheets'): 39 names contain '/', which their folders
        couldn't keep ('Memory / RAM' is saved as 'Memory RAM').
        Returns {"entries", "by_id", "by_breadcrumb", "by_segments", "by_path" (folder path),
        "by_key" (normalized leaf name -> [entries])}.
        """
        if cls._cached_index is not None and not force_refresh:
            return cls._cached_index

        entries: List[Dict[str, Any]] = []
        tmpl_dir = cls.get_templates_dir()
        for fpath in (sorted(tmpl_dir.rglob("*.xlsx")) if tmpl_dir.exists() else []):
            if fpath.name.startswith("~$"):  # Excel's lock file while a template is open
                continue
            rel_dir = fpath.parent.relative_to(tmpl_dir).as_posix()
            tmpl_id = re.search(r"-(\d+)-EXTERNAL", fpath.name)
            if rel_dir == "." or not tmpl_id:
                print(f"[MeeshoAdapter] Notice: {fpath.name} is not a category template (no category folder or id); ignored")
                continue
            entries.append({"id": tmpl_id.group(1), "path": rel_dir, "filename": fpath.name, "filepath": str(fpath)})

        # Real names: the exact folder path first for every leaf, then the same names with symbols
        # ignored, so a loose match never takes a folder that another leaf names exactly
        def loose(segments: List[str]) -> Tuple[str, ...]:
            return tuple(re.sub(r"[^a-z0-9]", "", s.lower()) for s in segments)

        by_path = {e["path"].lower(): e for e in entries}
        by_loose: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
        for e in entries:
            by_loose.setdefault(loose(e["path"].split("/")), []).append(e)
        unpaired = []
        for leaf in cls.load_category_taxonomy():
            e = by_path.get("/".join(leaf["segments"]).lower())
            if e is not None and "segments" not in e:
                e["segments"] = leaf["segments"]
            else:
                unpaired.append(leaf)
        for leaf in unpaired:
            fits = [e for e in by_loose.get(loose(leaf["segments"]), []) if "segments" not in e]
            if len(fits) == 1:
                fits[0]["segments"] = leaf["segments"]

        by_key: Dict[str, List[Dict[str, Any]]] = {}
        for e in entries:
            e.setdefault("segments", e["path"].split("/"))  # a template the taxonomy file doesn't list
            e["category"] = e["segments"][-1]
            e["normalized_category"] = cls._normalize_cat_key(e["category"])
            e["breadcrumb"] = BREADCRUMB_SEP.join(e["segments"])
            by_key.setdefault(e["normalized_category"], []).append(e)
        cls._cached_index = {
            "entries": entries,
            "by_id": {e["id"]: e for e in entries},
            "by_breadcrumb": {cls._breadcrumb_key(e["segments"]): e for e in entries},
            "by_segments": {tuple(e["segments"]): e for e in entries},
            "by_path": by_path,
            "by_key": by_key,
        }
        cls._loaded_templates = {}
        return cls._cached_index

    @classmethod
    def _breadcrumb_key(cls, segments: List[str]) -> str:
        return BREADCRUMB_SEP.join(s.strip().lower() for s in segments)

    @classmethod
    def template_by_ref(cls, ref: Any) -> Optional[Dict[str, Any]]:
        """
        The template a stored Meesho category means: Meesho's template id ('12776'), a breadcrumb
        ('Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets') or a template folder path.
        Exact matches only; None for anything else.
        """
        value = str(ref or "").strip()
        if not value:
            return None
        index = cls.template_index()
        if value.isdigit():
            return index["by_id"].get(value)
        if ">" in value:
            return index["by_breadcrumb"].get(cls._breadcrumb_key(value.split(">")))
        return index["by_path"].get(value.strip("/").lower())

    @classmethod
    def _load_template(cls, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Reads one template's layout: active data sheet ('<Category>-Fill this'), hierarchy, columns
        from Row 3, compulsory markers from Row 2 and dropdown options from the Validation Sheet.
        """
        fpath = entry["filepath"]
        if fpath in cls._loaded_templates:
            return cls._loaded_templates[fpath]
        try:
            wb = openpyxl.load_workbook(fpath, data_only=True)
        except Exception as e:
            print(f"[MeeshoAdapter] Notice: Could not read template {entry['filename']}: {e}")
            return None
        fill_sheet = next((s for s in wb.sheetnames if "-Fill this" in s), None)
        if not fill_sheet and len(wb.sheetnames) > 1:
            fill_sheet = wb.sheetnames[1]
        if not fill_sheet:
            print(f"[MeeshoAdapter] Notice: Template {entry['filename']} has no data sheet")
            return None

        sh = wb[fill_sheet]
        col_map = {}
        compulsory_cols = set()
        for col_idx in range(1, sh.max_column + 1):
            r2_val = str(sh.cell(2, col_idx).value or "").strip()
            if "* Compulsory" in r2_val or "Compulsory" in r2_val:
                compulsory_cols.add(col_idx)
            r3_val = str(sh.cell(3, col_idx).value or "").strip()
            col_map[col_idx] = r3_val.split("\n")[0].strip() if r3_val else f"Col_{col_idx}"

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
            **entry,
            "sheet_name": fill_sheet,
            "all_sheets": wb.sheetnames,
            "hierarchy": str(sh.cell(1, 1).value or ""),
            "total_columns": sh.max_column,
            "columns": col_map,
            "compulsory_columns": list(compulsory_cols),
            "dropdowns": dropdowns,
        }
        cls._loaded_templates[fpath] = template_info
        return template_info

    @classmethod
    def get_available_templates(cls) -> List[Dict[str, Any]]:
        """Every official template found, without opening them: id, category, breadcrumb and file."""
        return [
            {"id": e["id"], "category": e["category"], "breadcrumb": e["breadcrumb"], "filename": e["filename"]}
            for e in cls.template_index()["entries"]
        ]

    @classmethod
    def load_category_taxonomy(cls) -> List[Dict[str, Any]]:
        """All leaf categories of meeshoCategories.json, in the file's order: name, path and segments."""
        if cls._cached_categories is not None:
            return cls._cached_categories

        leafs: List[Dict[str, Any]] = []
        if MEESHO_CATEGORIES_FILE.exists():
            try:
                with open(MEESHO_CATEGORIES_FILE, "r", encoding="utf-8") as f:
                    tree = json.load(f)

                def walk(nodes: List[Dict[str, Any]], segments: List[str]):
                    for node in nodes:
                        here = segments + [node.get("name", "").strip()]
                        children = node.get("children", [])
                        if not children:
                            leafs.append({"name": here[-1], "path": "/".join(here), "segments": here})
                        else:
                            walk(children, here)

                walk(tree, [])
            except Exception as e:
                print(f"[MeeshoAdapter] Warning: Could not parse meeshoCategories.json: {e}")

        cls._cached_categories = leafs
        return leafs

    @classmethod
    def taxonomy_tree(cls) -> List[Dict[str, Any]]:
        """
        The category tree as the supplier panel shows it, four levels deep, for the category picker.
        Leaves are {"name", "id"} with Meesho's template id; leaves without a template are left out.
        """
        by_segments = cls.template_index()["by_segments"]
        roots: List[Dict[str, Any]] = []
        for leaf in cls.load_category_taxonomy():
            entry = by_segments.get(tuple(leaf["segments"]))
            if not entry:
                continue
            level = roots
            for name in leaf["segments"][:-1]:
                node = next((n for n in level if n["name"] == name and "children" in n), None)
                if node is None:
                    node = {"name": name, "children": []}
                    level.append(node)
                level = node["children"]
            level.append({"name": leaf["segments"][-1], "id": entry["id"]})
        return roots

    @classmethod
    def get_categories(cls, search: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Searches the official Meesho leaf categories by name or breadcrumb, each with its template.
        """
        q = (search or "").strip().lower()
        by_segments = cls.template_index()["by_segments"]

        results = []
        for item in cls.load_category_taxonomy():
            breadcrumb = BREADCRUMB_SEP.join(item["segments"])
            if not q or q in breadcrumb.lower() or q in item["path"].lower():
                # By full path only: several leaves share a name ("Bedsheets" under Home & Kitchen and Kids & Toys)
                tmpl = by_segments.get(tuple(item["segments"]))
                results.append({
                    "name": item["name"],
                    "path": breadcrumb,
                    "breadcrumb": breadcrumb,
                    "id": tmpl["id"] if tmpl else None,
                    "template_available": tmpl is not None,
                    "template_filename": tmpl["filename"] if tmpl else None,
                    "template_category": tmpl["category"] if tmpl else None,
                })
                if len(results) >= limit:
                    break

        return results

    @classmethod
    def template_candidates(cls, category_name: Optional[str]) -> List[Dict[str, Any]]:
        """
        Templates (index entries) a category name can mean, from the first rule that matches:
          1. A template id, breadcrumb or folder path (template_by_ref)
          2. The leaf name, normalized ('Bed Sheets' -> Bedsheets)
          3. The category's head noun ("Double Bedsheets" -> Bedsheets, "Brother & Sister T-Shirts" -> Tshirts),
             longest first so 'tshirts' wins over 'shirts'
          4. Head-noun synonyms ("Tees" -> Tshirts)
        Whole words only: "Steel bottles" and "Sweatshirts" don't match Bottles' or Shirts' templates.
        Used for suggestions; the export never picks a template by name (resolve_item_template).
        """
        if not category_name or not category_name.strip():
            return []
        hit = cls.template_by_ref(category_name)
        if hit:
            return [hit]
        by_key = cls.template_index()["by_key"]
        name = category_name.strip()
        if ">" in name:
            name = name.rsplit(">", 1)[-1]
        elif "/" in name:
            name = name.rsplit("/", 1)[-1]

        key = cls._normalize_cat_key(name)
        if key in by_key:
            return by_key[key]

        heads = [k for k in cls._head_keys(name) if k in by_key]
        if heads:
            longest = max(len(k) for k in heads)
            return [e for k in heads if len(k) == longest for e in by_key[k]]

        # Not 'bedding' or 'duvet': pet bedding or a duvet in the Bedsheets template fails Meesho QC
        synonyms = {"tee": "tshirt"}
        all_heads = cls._head_keys(name)
        for syn, target in synonyms.items():
            if syn in all_heads and target in by_key:
                return by_key[target]
        return []

    @classmethod
    def find_template(cls, category_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """The one template a category reference or name means, loaded; None when it means none or several."""
        candidates = cls.template_candidates(category_name)
        return cls._load_template(candidates[0]) if len(candidates) == 1 else None

    @classmethod
    def meesho_choice(cls, item: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        (value, source) of the seller's Meesho category for one product: the product's own
        'Meesho Category' (source "product"), else the default set for its category in Settings
        (source "category"), else (None, None).
        """
        own = _attr(cls._row_inputs(item)["attrs"], MEESHO_CATEGORY_ATTR)
        if own:
            return own, "product"
        category = cls._item_category(item).strip().lower()
        defaults = {k.strip().lower(): v for k, v in SettingsService.get_meesho_category_defaults().items()}
        if defaults.get(category):
            return defaults[category], "category"
        return None, None

    @classmethod
    def resolve_item_template(cls, item: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        (template, suggestions) for one product. The template comes only from the seller's choice
        (meesho_choice); a name match is never used to pick one. Without a usable choice the template
        is None and `suggestions` are the templates the product's category name could mean.
        """
        choice, _ = cls.meesho_choice(item)
        entry = cls.template_by_ref(choice) if choice else None
        if entry:
            loaded = cls._load_template(entry)
            return loaded, [entry]
        return None, cls.suggest_templates(item)

    @classmethod
    def suggest_templates(cls, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Templates the product's category name could mean, without those for another audience than
        its name states: "Women's straight kurta" isn't offered Men Fashion's Kurtas.
        """
        candidates = cls.template_candidates(cls._item_category(item))
        named = cls._named_audiences(cls._row_inputs(item)["name"])
        if not named:
            return candidates
        return [c for c in candidates if cls._audience(c["segments"][0]) in (None, *named)]

    @classmethod
    def _audience(cls, section: str) -> Optional[str]:
        """'men', 'women' or 'kids' for a top-level Meesho section that serves one audience."""
        for audience, sections in AUDIENCE_SECTIONS.items():
            if section.strip().lower() in sections:
                return audience
        return None

    @classmethod
    def _named_audiences(cls, text: str) -> set:
        """Audiences a product name states: "Women's flared kurta" -> {'women'}."""
        return {a for a, pattern in AUDIENCE_WORDS.items() if re.search(pattern, text or "", flags=re.IGNORECASE)}

    @classmethod
    def _item_category(cls, item: Dict[str, Any]) -> str:
        return getattr(item.get("product"), "category", None) or item.get("category") or "General"

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
        # Never shortened here: a title over Meesho's limit blocks the export (_upload_rule_problems)
        title = re.sub(r"<[^>]+>", "", draft_field("title") or name).strip()

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
            "has_draft": bool(draft),
            "approved": bool(draft_field("is_approved")),
            "draft_text": {"title": title, "description": desc, "bullets": bullets},
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
        # The seller's legal details from Settings, for products that don't carry their own
        if row.get("seller_details", {}).get(col_name):
            return row["seller_details"][col_name]

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
    def _upload_rule_problems(cls, row: Dict[str, Any], written: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Meesho's rules beyond the template's compulsory markers, all blocking: an approved Meesho draft,
        a Product Name within 100 characters without weight, dimensions, price or another marketplace's
        name, no word Meesho's QC flags, Meesho Price below MRP, a Wrong/Defective discount below the
        Meesho Price, and image links Meesho can use (made by its own uploader, never stock or local files).
        """
        problems = []

        def add(field: str, reason: str):
            problems.append({"sku": row["sku"], "field": field, "reason": reason, "blocking": True})

        if not row["has_draft"]:
            add("Meesho Draft", "no Meesho copy yet; generate it and approve it")
        elif not row["approved"]:
            add("Meesho Draft", "the Meesho draft isn't approved; review and approve it")

        name = row["title"]
        if len(name) > MEESHO_TITLE_LIMIT:
            add("Product Name", f"{len(name)} characters; Meesho allows {MEESHO_TITLE_LIMIT}. Shorten the draft title")
        for what, pattern in PRODUCT_NAME_RULES:
            m = re.search(pattern, name, flags=re.IGNORECASE)
            if m:
                add("Product Name", f"contains {what} ('{m.group(0).strip()}'), which Meesho doesn't allow in Product Name")
                break

        text = row.get("draft_text") or {}
        for field, value in (("Product Name", text.get("title")),
                             ("Product Description", " ".join([text.get("description") or "", *(text.get("bullets") or [])]))):
            flagged = [w for w in MEESHO_FLAGGED_WORDS if re.search(rf"\b{w}\b", value or "", flags=re.IGNORECASE)]
            if flagged:
                add(field, f"uses {', '.join(repr(w) for w in flagged)}, which Meesho's QC flags; edit the draft")

        price = _number(written.get("Meesho Price"))
        mrp = _number(written.get("MRP"))
        if price is not None and mrp is not None and price >= mrp:
            add("Meesho Price", f"₹{_fmt_num(price)} must be lower than the MRP (₹{_fmt_num(mrp)})")
        discount_col = next((k for k in written if "wrong/defective" in k.lower()), None)
        discount_raw = written.get(discount_col) if discount_col else None
        if discount_raw is not None and str(discount_raw).strip():
            discount = _number(discount_raw)
            if discount is None or discount < 0:
                add(discount_col, f"'{discount_raw}' is not an amount in ₹")
            elif price is not None and discount >= price:
                add(discount_col, f"₹{_fmt_num(discount)} discount must be below the Meesho Price (₹{_fmt_num(price)})")

        for col, value in written.items():
            if not col.lower().startswith("image") or value is None or not str(value).strip():
                continue
            link = str(value).strip()
            bad = next((label for label, pattern in UNUSABLE_IMAGE_LINKS if re.search(pattern, link, flags=re.IGNORECASE)), None)
            if not re.match(r"https?://", link, flags=re.IGNORECASE):
                add(col, f"'{link[:60]}' is not a web link; use the link Meesho's Images Bulk Upload gives")
            elif bad:
                add(col, f"{bad} link ({link[:60]}); Meesho needs the link its Images Bulk Upload gives for this photo")
        return problems

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
        if "columns" not in template_info:
            full_tmpl = (cls._load_template(template_info) if "filepath" in template_info
                         else cls.find_template(template_info.get("category")))
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
        seller_details = SettingsService.get_seller_details()

        # Ingest each product row starting at Row 5
        for idx, item in enumerate(products_with_drafts):
            target_row = 5 + idx
            row = cls._row_inputs(item)
            row["seller_details"] = seller_details
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
                            "reason": ("compulsory; set it once in Settings > Seller Details"
                                       if col_name in SELLER_DETAIL_FIELDS else
                                       "compulsory and missing from the product's data"),
                            "blocking": True,
                        })

                cell.value = val
                written[col_name] = val
            problems.extend({**pr, "category": category} for pr in cls._upload_rule_problems(row, written))
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
        All or nothing: fills each product's official template (resolve_item_template) only when
        every product given passes every check; otherwise raises MeeshoExportIncomplete listing all
        problems, and no file is made. The seller takes a product out of the upload instead of
        having it left out quietly.
          - One template: returns (xlsx_buf, xlsx media type, filename)
          - Several templates: returns a zip with one .xlsx per template
        force_zip zips even a single template's file (the dashboard's "Full Catalog (ZIP)"); several are always zipped.
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

        groups, unplaced = cls._group_by_template(products_with_drafts)
        generated_files: List[Tuple[str, io.BytesIO]] = []
        problems: List[Dict[str, Any]] = list(unplaced)
        leaf_counts: Dict[str, int] = {}
        for tmpl, _ in groups.values():
            leaf_counts[tmpl["category"]] = leaf_counts.get(tmpl["category"], 0) + 1

        for tmpl, tmpl_items in groups.values():
            try:
                buf = cls.populate_template(tmpl, tmpl_items)
            except MeeshoExportIncomplete as e:
                # Keep going so one response lists every template's problems
                problems.extend(e.problems)
                continue

            safe_cat = re.sub(r"[^a-zA-Z0-9_-]", "_", tmpl["category"])
            if leaf_counts[tmpl["category"]] > 1:
                # Men's and Women's Tshirts in one batch: the template's own id tells the files apart
                safe_cat += f"_{tmpl['id']}"
            generated_files.append((f"ListingPilot_Meesho_{safe_cat}.xlsx", buf))

        if any(p["blocking"] for p in problems):
            raise MeeshoExportIncomplete(problems)

        # One category: the .xlsx itself unless a zip was asked for; several: always a zip, so no file is dropped
        if len(generated_files) == 1 and not force_zip:
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
    def check_items(cls, products_with_drafts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        {sku: blocking problems} for an upload, by the export's own checks, without making a file.
        Checked together, so two selected products sharing a Product Name are both reported.
        """
        groups, unplaced = cls._group_by_template(products_with_drafts)
        problems: List[Dict[str, Any]] = list(unplaced)
        for tmpl, tmpl_items in groups.values():
            try:
                cls.populate_template(tmpl, tmpl_items)
            except MeeshoExportIncomplete as e:
                problems.extend(e.problems)
        by_sku: Dict[str, List[Dict[str, Any]]] = {cls._row_inputs(i)["sku"]: [] for i in products_with_drafts}
        for p in problems:
            if p["blocking"]:
                by_sku.setdefault(p["sku"], []).append(p)
        return by_sku

    @classmethod
    def build_fill_in_sheet(cls, products_with_drafts: List[Dict[str, Any]]) -> Optional[io.BytesIO]:
        """
        Workbook listing, per SKU, the Meesho fields its data is missing, laid out for the catalogue
        import (column headers are the template's own names, which the export reads back as attributes).
        Returns None when every product would export cleanly.
        """
        options: Dict[str, List[str]] = {}
        field_order: List[str] = []
        attr_names: Dict[str, str] = {}
        groups, template_problems = cls._group_by_template(products_with_drafts)
        # Products without a Meesho category block the export: listed under "What's wrong", and asked
        # for their Meesho Category so the next export can place them
        problems: List[Dict[str, Any]] = list(template_problems)
        for tmpl, tmpl_items in groups.values():
            for col_idx, col_name in tmpl["columns"].items():
                if col_name not in field_order:
                    field_order.append(col_name)
                attr_names.setdefault(col_name, cls._seller_attribute(tmpl["category"], col_name))
                if col_idx in tmpl.get("dropdowns", {}):
                    options.setdefault(col_name, tmpl["dropdowns"][col_idx])
            try:
                cls.populate_template(tmpl, tmpl_items)
            except MeeshoExportIncomplete as e:
                problems.extend(e.problems)
        blocking = [p for p in problems if p["blocking"]]
        if not blocking and not template_problems:
            return None

        image_fields = ["Image 1 (Front)", "Image 2", "Image 3", "Image 4"]
        # Product Name problems are fixed by regenerating the draft, and seller details once in
        # Settings, not by filling a cell per SKU
        fields = [f for f in field_order if any(p["field"] == f for p in blocking)
                  and f != "Product Name" and not f.lower().startswith("image") and f not in SELLER_DETAIL_FIELDS]
        if template_problems:
            fields.insert(0, MEESHO_CATEGORY_ATTR)
            attr_names[MEESHO_CATEGORY_ATTR] = MEESHO_CATEGORY_ATTR
            options[MEESHO_CATEGORY_ATTR] = sorted(e["breadcrumb"] for e in cls.template_index()["entries"])
            blocking = blocking + [{**p, "field": MEESHO_CATEGORY_ATTR} for p in template_problems]

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
    def seller_fields(cls, tmpl: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """{attribute name: {"field": template column, "options": [...]}} for every column of a loaded template."""
        if not tmpl:
            return {}
        dropdowns = tmpl.get("dropdowns", {})
        return {
            cls._seller_attribute(tmpl["category"], name): {"field": name, "options": dropdowns.get(idx, [])}
            for idx, name in tmpl["columns"].items()
        }

    @classmethod
    def missing_fields(cls, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        What one product still needs before the Meesho export accepts it, found by running the export's
        own checks. `fields` are the ones the seller fills (the attribute each is saved under and the
        template's exact options); `seller` are seller details missing from Settings; `other` are
        blockers a value can't fix (images, Product Name).
        """
        category = cls._item_category(item)
        tmpl, suggestions = cls.resolve_item_template(item)
        _, source = cls.meesho_choice(item)
        meesho_category = {
            "id": tmpl["id"] if tmpl else None,
            "breadcrumb": tmpl["breadcrumb"] if tmpl else None,
            "source": source if tmpl else None,  # "product" or "category" (the category's default)
            # Templates the product's category name could mean; the seller still picks one
            "suggestions": [] if tmpl else [{"id": s["id"], "breadcrumb": s["breadcrumb"]} for s in suggestions],
        }
        if not tmpl:
            return {"category": category, "template": None, "meesho_category": meesho_category,
                    "fields": [], "seller": [],
                    "other": [{"field": "Template", "reason": cls._template_problem(item, suggestions)["reason"]}]}
        try:
            cls.populate_template(tmpl, [item])
            problems: List[Dict[str, Any]] = []
        except MeeshoExportIncomplete as e:
            problems = [p for p in e.problems if p["blocking"]]

        by_field = {spec["field"]: (attr, spec["options"]) for attr, spec in cls.seller_fields(tmpl).items()}
        fields, seller, other = [], [], []
        for p in problems:
            name = p["field"]
            if name in SELLER_DETAIL_FIELDS:
                seller.append(name)
                continue
            if name == "Product Name" or name.lower().startswith("image") or name not in by_field:
                other.append({"field": name, "reason": p["reason"]})
                continue
            attr, options = by_field[name]
            fields.append({"field": name, "attribute": attr, "options": options, "reason": p["reason"]})
        return {"category": category, "template": tmpl["filename"], "meesho_category": meesho_category,
                "fields": fields, "seller": seller, "other": other}

    @classmethod
    def _group_by_template(cls, products_with_drafts: List[Dict[str, Any]]) -> Tuple[Dict[str, Tuple[Dict[str, Any], List[Dict[str, Any]]]], List[Dict[str, Any]]]:
        """
        ({template filepath: (template, items)}, problems): each item under the one template it
        resolves to, and a non-blocking 'Template' problem for each item with none or several.
        """
        groups: Dict[str, Tuple[Dict[str, Any], List[Dict[str, Any]]]] = {}
        problems: List[Dict[str, Any]] = []
        for item in products_with_drafts:
            tmpl, candidates = cls.resolve_item_template(item)
            if tmpl:
                groups.setdefault(tmpl["filepath"], (tmpl, []))[1].append(item)
            else:
                problems.append(cls._template_problem(item, candidates))
        return groups, problems

    @classmethod
    def generate_bulk_upload_file(
        cls,
        category: str,
        products_with_drafts: List[Dict[str, Any]]
    ) -> io.BytesIO:
        """Fills the official template for one category; there is no substitute layout."""
        candidates = cls.template_candidates(category)
        if len(candidates) != 1:
            raise MeeshoExportIncomplete([
                {**cls._template_problem({**item, "category": category}, candidates), "blocking": True}
                for item in products_with_drafts
            ])
        return cls.populate_template(cls._load_template(candidates[0]), products_with_drafts)

    @classmethod
    def _template_problem(cls, item: Dict[str, Any], suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Meesho only accepts its own category template, so a product without a Meesho category the
        seller chose (it is never guessed) can't be exported until one is picked.
        """
        category = cls._item_category(item)
        choice, source = cls.meesho_choice(item)
        entry = cls.template_by_ref(choice) if choice else None
        where = "set on the product" if source == "product" else f"the default for '{category}'"
        if entry:
            reason = f"the template file for {entry['breadcrumb']} ({entry['filename']}) couldn't be read"
        elif choice:
            reason = f"'{choice}' ({where}) is not an official Meesho category; pick it again"
        else:
            reason = f"no Meesho category chosen for this product or for '{category}'; pick it as in the supplier panel"
            if suggestions:
                reason += " (suggested: " + "; ".join(s["breadcrumb"] for s in suggestions[:5]) + ")"
        return {
            "sku": cls._row_inputs(item)["sku"], "category": category, "field": "Template",
            "reason": reason, "candidates": [s["breadcrumb"] for s in suggestions], "blocking": True,
        }
