import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import io

CATEGORIES_INFO = [
    {
        "category": "Bedsheets",
        "required_attrs": ["Material", "Size", "Thread count", "Care"],
        "recommended_attrs": ["Colour", "Pattern", "Included"],
        "min_images": 3,
        "sample": {
            "sku": "JBP-101",
            "name": "Hand block print double bedsheet with 2 pillow covers",
            "category": "Bedsheets",
            "brand": "Gulmohar Home",
            "mrp": 1599,
            "price": 1299,
            "stock": 40,
            "images": "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af",
            "material": "100% cotton",
            "size": "90 x 100 in (double)",
            "colour": "Indigo and white",
            "pattern": "Floral, hand block print",
            "included": "1 bedsheet + 2 pillow covers (17 x 27 in)",
            "care": "Machine wash cold with similar colours",
            "weight": "850 g",
            "notes": "Traditional Sanganeri hand block print on premium cotton"
        }
    },
    {
        "category": "Pooja items",
        "required_attrs": ["Material", "Dimensions", "Finish"],
        "recommended_attrs": ["Count", "Weight", "Occasion"],
        "min_images": 3,
        "sample": {
            "sku": "BRS-220",
            "name": "Solid brass diya, set of 2",
            "category": "Pooja items",
            "brand": "Gulmohar Home",
            "mrp": 999,
            "price": 749,
            "stock": 120,
            "images": "https://images.unsplash.com/photo-1605371924599-2d0365da1ae0",
            "material": "Solid brass",
            "size": "4 x 4 x 2.5 in each",
            "colour": "Antique gold",
            "pattern": "Hand-polished traditional floral etching",
            "included": "2 oil lamps",
            "care": "Wipe with lemon and salt or brass polish",
            "weight": "350 g (set)",
            "notes": "Ideal for Diwali, griha pravesh and temple altar"
        }
    },
    {
        "category": "Kurtas",
        "required_attrs": ["Material", "Fit", "Sleeve", "Length", "Care"],
        "recommended_attrs": ["Colour", "Print", "Size"],
        "min_images": 3,
        "sample": {
            "sku": "KRT-310",
            "name": "Women's indigo dabu print straight kurta",
            "category": "Kurtas",
            "brand": "Gulmohar Home",
            "mrp": 1299,
            "price": 899,
            "stock": 65,
            "images": "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b",
            "material": "Cotton cambric",
            "size": "M (Bust 38 in, Length 46 in)",
            "colour": "Indigo",
            "pattern": "Dabu hand block print",
            "included": "1 Kurta",
            "care": "Hand wash cold separately in shade",
            "weight": "250 g",
            "notes": "Mud-resist dabu print technique from Bagru, Rajasthan"
        }
    },
    {
        "category": "Planters",
        "required_attrs": ["Material", "Dimensions", "Drainage"],
        "recommended_attrs": ["Colour", "Use"],
        "min_images": 3,
        "sample": {
            "sku": "BLU-415",
            "name": "Jaipur blue pottery ceramic planter 6 inch",
            "category": "Planters",
            "brand": "Gulmohar Home",
            "mrp": 1299,
            "price": 1050,
            "stock": 25,
            "images": "https://images.unsplash.com/photo-1485955900006-10f4d324d411",
            "material": "Hand-painted blue pottery ceramic",
            "size": "6 x 6 x 5.5 in",
            "colour": "Cobalt blue and white",
            "pattern": "Traditional Jaipur floral motif",
            "included": "1 Planter with drainage plug",
            "care": "Wipe clean with a damp cloth",
            "weight": "750 g",
            "notes": "Indoor plants, succulents and tabletop decor"
        }
    },
    {
        "category": "Ethnic footwear",
        "required_attrs": ["Upper material", "Sole", "Sizes", "Closure"],
        "recommended_attrs": ["Colour", "Occasion"],
        "min_images": 3,
        "sample": {
            "sku": "MJR-520",
            "name": "Men's handcrafted genuine leather mojari with gold embroidery",
            "category": "Ethnic footwear",
            "brand": "Gulmohar Home",
            "mrp": 1999,
            "price": 1499,
            "stock": 30,
            "images": "https://images.unsplash.com/photo-1549298916-b41d501d3772",
            "material": "Genuine leather upper & leather sole",
            "size": "UK 8 (Sizes available: UK 6 to 11)",
            "colour": "Tan with gold embroidery",
            "pattern": "Hand-stitched zari thread work",
            "included": "1 pair of juttis + fabric dust bag",
            "care": "Clean with a soft brush, avoid water",
            "weight": "420 g",
            "notes": "Handcrafted by hereditary artisans in Jodhpur"
        }
    },
    {
        "category": "Quilts",
        "required_attrs": ["Fill", "Outer", "Size", "Weight", "Care"],
        "recommended_attrs": ["Colour", "Pattern"],
        "min_images": 3,
        "sample": {
            "sku": "QLT-610",
            "name": "Jaipuri ultra-light cotton razai single bed",
            "category": "Quilts",
            "brand": "Gulmohar Home",
            "mrp": 2499,
            "price": 1899,
            "stock": 18,
            "images": "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2",
            "material": "500 g hand-carded cotton fill, 100% cotton voile outer",
            "size": "Single, 60 x 90 in",
            "colour": "Rose pink",
            "pattern": "Hand block print floral sanganeri",
            "included": "1 Single Razai + protective cotton zip cover",
            "care": "Dry clean recommended",
            "weight": "500 g",
            "notes": "Ultra-lightweight warmth for AC and mild winters"
        }
    }
]

COLUMNS = [
    ("SKU *", "Unique product SKU code (e.g. JBP-101)", True),
    ("Product Name *", "Title or base name of product", True),
    ("Category *", "Category name (Bedsheets, Pooja items, Kurtas, Planters, etc.)", True),
    ("Brand *", "Brand name (defaults to Gulmohar Home)", True),
    ("MRP (INR)", "Maximum Retail Price printed on tag/box", False),
    ("Selling Price (INR) *", "Current selling price on marketplaces", True),
    ("Stock Quantity *", "Available inventory count", True),
    ("Image URLs", "Comma-separated photo URLs", False),
    ("Material", "Fabric / metal / substance specs", False),
    ("Size / Dimensions", "Product dimensions or apparel size", False),
    ("Colour", "Primary and secondary colours", False),
    ("Pattern / Finish", "Print, texture or surface polish", False),
    ("Included Items", "Package contents (e.g. 1 bedsheet + 2 pillow covers)", False),
    ("Care Instructions", "Washing, cleaning or storage directions", False),
    ("Weight", "Net weight with unit (e.g. 850 g)", False),
    ("Occasion / Notes", "Usage notes, target occasion or key features", False),
]

def generate_master_catalogue_template() -> io.BytesIO:
    """Generates an Excel workbook template with styling, sample data, and rule instructions."""
    wb = openpyxl.Workbook()
    
    # -------------------------------------------------------------
    # Styling Palette: Sleek Forest Green & Clean Off-White
    # -------------------------------------------------------------
    header_fill = PatternFill(start_color="0D6B58", end_color="0D6B58", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    
    subhead_fill = PatternFill(start_color="DCEFE9", end_color="DCEFE9", fill_type="solid")
    subhead_font = Font(name="Segoe UI", size=10, bold=True, color="0D6B58")
    
    regular_font = Font(name="Segoe UI", size=10)
    bold_font = Font(name="Segoe UI", size=10, bold=True)
    muted_font = Font(name="Segoe UI", size=9, color="5B6964", italic=True)
    
    thin_border = Border(
        left=Side(style='thin', color='DBE1DC'),
        right=Side(style='thin', color='DBE1DC'),
        top=Side(style='thin', color='DBE1DC'),
        bottom=Side(style='thin', color='DBE1DC')
    )
    
    # -------------------------------------------------------------
    # Sheet 1: Master Catalogue (Ready for User Data Entry)
    # -------------------------------------------------------------
    ws_cat = wb.active
    ws_cat.title = "Master Catalogue"
    ws_cat.views.sheetView[0].showGridLines = True
    
    # Row 1: Column Headers
    for col_idx, (col_name, _, is_req) in enumerate(COLUMNS, start=1):
        cell = ws_cat.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 5, 6, 7] else "left", vertical="center", wrap_text=True)
        cell.border = thin_border
    
    # Row 2: Helpful Placeholder / Hint row
    for col_idx, (_, hint, _) in enumerate(COLUMNS, start=1):
        cell = ws_cat.cell(row=2, column=col_idx, value=f"({hint})")
        cell.fill = subhead_fill
        cell.font = muted_font
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell.border = thin_border
    
    # Add empty rows ready for user entry (rows 3 to 15)
    for r in range(3, 16):
        for col_idx in range(1, len(COLUMNS) + 1):
            cell = ws_cat.cell(row=r, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            if col_idx == 4:  # Brand default
                cell.value = "Gulmohar Home"
    
    ws_cat.row_dimensions[1].height = 28
    ws_cat.row_dimensions[2].height = 24
    
    # -------------------------------------------------------------
    # Sheet 2: Sample Pilot Products
    # -------------------------------------------------------------
    ws_samples = wb.create_sheet(title="Sample Pilot Products")
    ws_samples.views.sheetView[0].showGridLines = True
    
    for col_idx, (col_name, _, _) in enumerate(COLUMNS, start=1):
        cell = ws_samples.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 5, 6, 7] else "left", vertical="center")
        cell.border = thin_border
        
    for row_idx, item in enumerate(CATEGORIES_INFO, start=2):
        s = item["sample"]
        row_values = [
            s["sku"],
            s["name"],
            s["category"],
            s["brand"],
            s["mrp"],
            s["price"],
            s["stock"],
            s["images"],
            s["material"],
            s["size"],
            s["colour"],
            s["pattern"],
            s["included"],
            s["care"],
            s["weight"],
            s["notes"]
        ]
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws_samples.cell(row=row_idx, column=col_idx, value=val)
            cell.font = regular_font
            cell.border = thin_border
            if col_idx in [5, 6]:
                cell.number_format = '₹#,##0'
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in [1, 7]:
                cell.alignment = Alignment(horizontal="center")
    
    ws_samples.row_dimensions[1].height = 28
    
    # -------------------------------------------------------------
    # Sheet 3: Instructions & Rules
    # -------------------------------------------------------------
    ws_rules = wb.create_sheet(title="Instructions & Rules")
    ws_rules.views.sheetView[0].showGridLines = True
    
    instructions = [
        ("ListingPilot Master Catalogue Instructions", header_fill, header_font),
        ("1. General Instructions", subhead_fill, subhead_font),
        ("• Each row represents one sellable SKU. SKUs must be unique across the catalogue.", None, regular_font),
        ("• Columns marked with an asterisk (*) are mandatory.", None, regular_font),
        ("• Enter accurate attributes (Size, Material, Care) so AI can write high-converting listings without guessing.", None, regular_font),
        ("• Avoid entering promotional terms ('Free delivery', 'Best seller', '100% guarantee') in names or notes, as marketplaces prohibit them.", None, regular_font),
        ("2. Image Guidelines", subhead_fill, subhead_font),
        ("• Supply at least 3 photos per product; 5 or more are strongly recommended for high conversion.", None, regular_font),
        ("• The primary image MUST be on a clean, plain white background without watermarks or text overlay.", None, regular_font),
        ("• Separate multiple image URLs with commas.", None, regular_font),
        ("3. Supported Categories & Minimum Required Fields", subhead_fill, subhead_font),
    ]
    
    for cat in CATEGORIES_INFO:
        req_str = ", ".join(cat["required_attrs"])
        rec_str = ", ".join(cat["recommended_attrs"])
        instructions.append((f"• {cat['category']}: Required attributes -> [{req_str}]. Recommended -> [{rec_str}]. Minimum {cat['min_images']} photos.", None, regular_font))
        
    instructions.extend([
        ("4. Import Compatibility", subhead_fill, subhead_font),
        ("• You can upload this Excel file, a CSV export, or standard Tally stock exports.", None, regular_font),
        ("• ListingPilot automatically parses and validates all columns before anything is submitted.", None, regular_font),
    ])
    
    for r_idx, (text, fill, font) in enumerate(instructions, start=1):
        cell = ws_rules.cell(row=r_idx, column=1, value=text)
        if fill:
            cell.fill = fill
        if font:
            cell.font = font
        ws_rules.row_dimensions[r_idx].height = 22 if fill else 19
        
    ws_rules.column_dimensions["A"].width = 110
    
    # -------------------------------------------------------------
    # Auto-adjust column widths for Master Catalogue & Sample sheets
    # -------------------------------------------------------------
    for ws in [ws_cat, ws_samples]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if cell.row == 2:  # Ignore long hint strings when calculating width
                    continue
                max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 14)
            
    # Save to memory buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
