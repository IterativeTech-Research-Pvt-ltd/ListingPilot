"""
Pilot catalogue: 19 products across six seller categories, each complete for its Meesho template
(every compulsory field, with the template's exact values) except photos, which come from the
seller's product-images bucket (PRODUCT_IMAGES).

    .venv\\Scripts\\python.exe backend/app/seeds/seed_pilot_data.py            adds missing SKUs only
    .venv\\Scripts\\python.exe backend/app/seeds/seed_pilot_data.py --replace  deletes these SKUs (and their
        drafts), seeds them again, and sets Seller Details and the Meesho category defaults

The values are demo data written to look real; replace them with the seller's own before a real upload.
"""
import os
import sys

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.database import SessionLocal, engine, Base, check_connection
from app.models.product import Product
from app.models.draft import ListingDraft
from app.services.catalogue_service import CatalogueService
from app.services.settings_service import SettingsService
from app.services.meesho_adapter import MeeshoAdapter, MEESHO_CATEGORY_ATTR, MEESHO_ATTR_PREFIX

BRAND = "Gulmohar Home"

# Demo legal details for Settings > Seller Details (set by --replace only)
SELLER_DETAILS = {
    "Country of Origin": "India",
    "Manufacturer Name": "Gulmohar Home Textiles",
    "Manufacturer Address": "Plot 14, Sanganer Industrial Area, Jaipur, Rajasthan",
    "Manufacturer Pincode": "302029",
    "Packer Name": "Gulmohar Home Textiles",
    "Packer Address": "Plot 14, Sanganer Industrial Area, Jaipur, Rajasthan",
    "Packer Pincode": "302029",
    "Importer Name": "Gulmohar Home Textiles",
    "Importer Address": "Plot 14, Sanganer Industrial Area, Jaipur, Rajasthan",
    "Importer Pincode": "302029",
}

# Meesho template per seller category (set by --replace only); products in another Meesho category
# carry their own 'Meesho Category' (men's kurta, diyas, both footwear)
MEESHO_CATEGORY_DEFAULTS = {
    "Bedsheets": "12776",    # Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets
    "Pooja items": "12811",  # Home & Kitchen > Home Decor > Puja Accessories > Puja Articles
    "Kurtas": "10004",       # Women Fashion > Ethnic Wear > Kurtis, Sets & Fabrics > Kurtis
    "Planters": "13367",     # Home & Kitchen > Gardening > Plant Containers > Planter
    "Quilts": "15875",       # Home & Kitchen > Home Furnishings > Blankets, Throws & Quilts > Quilts
}

# Signed links from the seller's Supabase product-images bucket (5-year expiry, made 3 Nov 2026), Image 1
# first: {sku: [links]}. These are free-licence Unsplash stand-ins (assets/product-images/) for testing
# the workflow, not photos of these products: replace them with the seller's own before a real upload.
PRODUCT_IMAGES = {
    "BLU-415": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/BLU-415_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9CTFUtNDE1XzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYyMywiZXhwIjoxOTUxMzg0NjIzfQ.j-NeBflXwSL7pid_-mhepSe66nvfFDRkijufx7HrQcn_5aJwOQMbQsdGcO8wy1z3fTTwvdRQJixUke5erRKZAw",
    ],
    "BLU-416": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/BLU-416_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9CTFUtNDE2XzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYyNCwiZXhwIjoxOTUxMzg0NjI0fQ.88jJ8Rh0VsiYfRwWQy8fllGmey2sR13OoPlOA_OsLtdoQAY41OTOb44n4bRZpuhpiNZdrxxTVs-OZ45KRU0srA",
    ],
    "BRS-220": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/BRS-220_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9CUlMtMjIwXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYyNywiZXhwIjoxOTUxMzg0NjI3fQ.Q5Ixe-R7ieWuXhDhR6gq6is2_s3BKPEor6n55DrZwFrs6WvEBGx8-agRAwWSYn7VnKlQLpN-soSsXVjypdo_Xg",
    ],
    "BRS-221": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/BRS-221_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9CUlMtMjIxXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYyOCwiZXhwIjoxOTUxMzg0NjI4fQ.pqsWUUtgjy2tYcN8_XniYrPMUeEwTzpttXb8cWD__bTIi-Sxi3koR7m0bqq9B4LYh4q_AjDZ_Woa5Yxs37rBtA",
    ],
    "BRS-222": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/BRS-222_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9CUlMtMjIyXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYyOSwiZXhwIjoxOTUxMzg0NjI5fQ.5LDiEJSAP_gr2rZHZunlXuFkklWv8M-FyUihuX-I1Lk3-x-ehwP_EHoZnk8IurD4T4pMCBjvp9fdCIFpht7iqg",
    ],
    "BRS-223": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/BRS-223_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9CUlMtMjIzXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYyOSwiZXhwIjoxOTUxMzg0NjI5fQ.9zRBogon-xcczUb3Spgys-kqXEUeGt0NkndWUec1vZuh9d6v8qAKd612ReIsM_nd3uts57uk3gDYXFOwGxX00g",
    ],
    "BRS-224": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/BRS-224_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9CUlMtMjI0XzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzMCwiZXhwIjoxOTUxMzg0NjMwfQ.I0VjO1rJyo4C61zlBeYcRBGGcPgVrG9-oiIDrO6_A_u3Ixgxmy30j_KCkRy9Ivht2WxCM31u_quaeKitP1xNwg",
    ],
    "JBP-101": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/JBP-101_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9KQlAtMTAxXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzMSwiZXhwIjoxOTUxMzg0NjMxfQ.1LYYvSi5ZCiJ97mGPA5dI2GR5dZKi6oUSlsaiP1X2KyX-sM6gH9wVym9oEohzFAymfSbexIDfuDyzncgywy7Lg",
    ],
    "JBP-102": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/JBP-102_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9KQlAtMTAyXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzMywiZXhwIjoxOTUxMzg0NjMzfQ.GfmHK8yOhGc-WALCwo3jg5McXk5Z3s2Ir7lDwniQD0nTGOzgiAiBgiyli8ESzMwRyl0a5B6OCxR9BEJ4SVZ7Zg",
    ],
    "JBP-103": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/JBP-103_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9KQlAtMTAzXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzNCwiZXhwIjoxOTUxMzg0NjM0fQ.qKWYTlWsRZvG7ZcA6rsFQBEp8Q-4kXBPV3ahOLWjg1nQ1uoIVpdCDCORIuc55ATdJVLw7b2SuxA0cuVn3aO6qA",
    ],
    "JBP-104": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/JBP-104_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9KQlAtMTA0XzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzNSwiZXhwIjoxOTUxMzg0NjM1fQ.o7u2tkq8lGkgjsMB-pdQfkJ0Pd4G7qf_fNfpdVpI9MME862eUvLSPETtF6_nsjqd0E08XAbtl-wRYCdhC-9F3w",
    ],
    "JBP-105": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/JBP-105_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9KQlAtMTA1XzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzNiwiZXhwIjoxOTUxMzg0NjM2fQ.Clux_3Sf2sxtG4_nSYUJRQh3tW2ZAFVCh5Rxoxgw49zPGL89eizYc_MnUyGY9WApmNpiHr4wPw9KYDlQwaisag",
    ],
    "KRT-310": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/KRT-310_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9LUlQtMzEwXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzNywiZXhwIjoxOTUxMzg0NjM3fQ.ZhGphhYRmTJqdMJUVC99kKKUaIYQRSQ8Q1RnIyYdPRGh2YVeZgnVw3P-pKmS4QkjRrgrYd6SA9t9EapNzCNXkA",
    ],
    "KRT-311": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/KRT-311_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9LUlQtMzExXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzOCwiZXhwIjoxOTUxMzg0NjM4fQ.lDRNCzjg7vx8_TxCx4Md10hegcY9r9TSNontKquhKASdeDae1rRokBcrOSGYE10ONmXw6F7lB8rWRNMKgoJlHQ",
    ],
    "KRT-312": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/KRT-312_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9LUlQtMzEyXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDYzOSwiZXhwIjoxOTUxMzg0NjM5fQ.IhQqELt5yjfuLQL5YlKZVP70TK_PmH2AYhK3ouA-GEfl5hzwb95MrzepHtSse4l8EZ6luIjI8q3ncXLIEUhvnA",
    ],
    "MJR-520": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/MJR-520_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9NSlItNTIwXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDY0MCwiZXhwIjoxOTUxMzg0NjQwfQ.eCGPhwwEMxyA3u-P1hZOvovOIzh-E93uLPVzDL4Bb3aJmjnf4g71PBiQTrrEot3w0151_v4x5h2dLHr6DGXPUA",
    ],
    "MJR-521": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/MJR-521_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9NSlItNTIxXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDY0MCwiZXhwIjoxOTUxMzg0NjQwfQ.jP0Z0Y4FiD9Ojz8qBA5FTMRqaB0h9BDo4C4nHyGmNulbnJ5JXqxLs9jmW0TiyJ5H-BrZBT4ZzrEcSdfFyFfxVA",
    ],
    "QLT-610": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/QLT-610_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9RTFQtNjEwXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDY0MSwiZXhwIjoxOTUxMzg0NjQxfQ.eeDWllj_EeHfVSchVVNi5bPMUsqp1dBt1pVb99fbbR3ObMgEWwl0IWHru3WW4Yefukk8oS7rdizqbbJsPqY1OA",
    ],
    "QLT-611": [
        "https://ivpbdqxfqaloyxceufba.supabase.co/storage/v1/object/sign/product-images/QLT-611_1.jpg?token=eyJraWQiOiI3MDQ3ZjcyMS1mMjYyLTQxMDMtOTdiNS1iZjAwMGFhZjNmNWMiLCJhbGciOiJIUzUxMiJ9.eyJ1cmwiOiJwcm9kdWN0LWltYWdlcy9RTFQtNjExXzEuanBnIiwic2NvcGUiOiJkb3dubG9hZCIsImlhdCI6MTc5MzcwNDY0MiwiZXhwIjoxOTUxMzg0NjQyfQ.73mOQNLFvvrZDjoKV3ldY3RO0WxVEGyK59wsqU-xICeHsrp0YkgkTi9Ax40wlQk6Yp20gkVgcHwt9OYQxITqaA",
    ],
}

# Each product's `meesho` values are the seller's exact Meesho values, saved as 'Meesho <column>'
# attributes; columns the export fills from the descriptive attributes aren't repeated there
_PRODUCTS = [
    # Bedsheets -> 12776
    {
        "sku": "JBP-101", "name": "Hand block print double bedsheet with 2 pillow covers", "category": "Bedsheets",
        "mrp": 1699, "price": 1299, "stock": 40,
        "attributes": {
            "Material": "100% cotton", "Size": "90 x 100 in (double)", "Thread count": "180 TC",
            "Colour": "Indigo and white", "Pattern": "Floral, hand block print",
            "Included": "1 bedsheet + 2 pillow covers (17 x 27 in)", "Care": "Machine wash cold",
        },
        "meesho": {"Variation": "Double", "Size": "Double Queen", "Color": "Blue", "Fabric": "Cotton",
                   "Care Instructions": "Machine Wash Only", "Ideal For": "Adult", "Ideal Season": "Summer",
                   "Occassion Type": "Others", "Quality": "Regular", "Type": "Flat Sheets",
                   "HSN ID": "630221", "GST %": "5", "Net Weight (gms)": "650", "Net Quantity (N)": "1"},
        "description": "Traditional Sanganeri hand block print on 100% cotton",
    },
    {
        "sku": "JBP-102", "name": "Jaipuri Mughal motif king bedsheet with 2 pillow covers", "category": "Bedsheets",
        "mrp": 1999, "price": 1599, "stock": 25,
        "attributes": {
            "Material": "100% combed cotton", "Size": "108 x 108 in (king)", "Thread count": "210 TC",
            "Colour": "Maroon and Beige", "Pattern": "Mughal floral buti print",
            "Included": "1 King Bedsheet + 2 Pillow Shams (18 x 28 in)", "Care": "Gentle machine wash cold",
        },
        "meesho": {"Variation": "King", "Size": "Double King", "Color": "Maroon", "Fabric": "Cotton",
                   "Print or Pattern Type": "Floral", "Care Instructions": "Machine Wash Only", "Ideal For": "Adult",
                   "Ideal Season": "Summer", "Occassion Type": "Others", "Quality": "Fine", "Type": "Flat Sheets",
                   "HSN ID": "630221", "GST %": "5", "Net Weight (gms)": "900", "Net Quantity (N)": "1"},
        "description": "Mughal buti hand block printed bedsheet for king mattresses",
    },
    {
        "sku": "JBP-103", "name": "Bagru natural dye block print double bedsheet", "category": "Bedsheets",
        "mrp": 1799, "price": 1399, "stock": 35,
        "attributes": {
            "Material": "Cotton", "Size": "90 x 100 in (double)", "Thread count": "180 TC",
            "Colour": "Mustard and Black", "Pattern": "Geometric Bagru hand block print",
            "Included": "1 Double Sheet + 2 Pillow Covers", "Care": "Hand wash for the first 2 washes, then machine wash",
        },
        "meesho": {"Variation": "Double", "Size": "Double Queen", "Color": "Mustard", "Fabric": "Cotton",
                   "Print or Pattern Type": "Geometric", "Care Instructions": "Hand and Machine Wash",
                   "Ideal For": "Adult", "Ideal Season": "Summer", "Occassion Type": "Others", "Quality": "Regular",
                   "Type": "Flat Sheets", "HSN ID": "630221", "GST %": "5", "Net Weight (gms)": "700",
                   "Net Quantity (N)": "1"},
        "description": "Block printed in Bagru with vegetable and plant-based dyes",
    },
    {
        "sku": "JBP-104", "name": "Pastel lotus print single bedsheet with 1 pillow cover", "category": "Bedsheets",
        "mrp": 1099, "price": 799, "stock": 50,
        "attributes": {
            "Material": "Cotton", "Size": "60 x 90 in (single)", "Thread count": "160 TC",
            "Colour": "Sage Green and Pink", "Pattern": "Lotus floral motif",
            "Included": "1 Single Bedsheet + 1 Pillow Cover", "Care": "Machine wash cold",
        },
        "meesho": {"Variation": "Single", "Size": "Single", "Color": "Green", "Fabric": "Cotton",
                   "Print or Pattern Type": "Floral", "Care Instructions": "Machine Wash Only", "Ideal For": "Kids", "Dimensions (inches)": "60*90-(Single)",
                   "Ideal Season": "Summer", "Occassion Type": "Others", "Quality": "Regular", "Type": "Flat Sheets",
                   "HSN ID": "630221", "GST %": "5", "Net Weight (gms)": "450", "Net Quantity (N)": "1"},
        "description": "Pastel lotus print for single beds and kids' bedrooms",
    },
    {
        "sku": "JBP-105", "name": "Indigo dabu print fitted double bedsheet with elastic", "category": "Bedsheets",
        "mrp": 1899, "price": 1499, "stock": 30,
        "attributes": {
            "Material": "100% cotton", "Size": "72 x 78 in + 10 in drop (fitted double)", "Thread count": "200 TC",
            "Colour": "Deep Indigo", "Pattern": "Dabu mud-resist geometric block print",
            "Included": "1 Fitted Sheet + 2 Pillow Covers", "Care": "Machine wash cold separately",
        },
        "meesho": {"Variation": "Double", "Size": "Double Queen", "Color": "Navy Blue", "Fabric": "Cotton",
                   "Print or Pattern Type": "Geometric", "Care Instructions": "Machine Wash Only", "Ideal For": "Adult",
                   "Ideal Season": "Summer", "Occassion Type": "Others", "Quality": "Regular",
                   "Type": "Fitted Bedsheets", "HSN ID": "630221", "GST %": "5", "Net Weight (gms)": "750",
                   "Net Quantity (N)": "1"},
        "description": "Fitted sheet with elastic all around, for mattresses up to 10 in deep",
    },
    # Pooja items -> 12811 Puja Articles; diyas -> 13323 Diyas & Lanterns
    {
        "sku": "BRS-220", "name": "Solid brass diya, set of 2", "category": "Pooja items",
        "mrp": 999, "price": 749, "stock": 120,
        "attributes": {
            MEESHO_CATEGORY_ATTR: "13323", "Material": "Solid brass", "Dimensions": "4 x 4 x 2.5 in",
            "Count": "Set of 2", "Finish": "Hand-polished antique gold", "Weight": "350 g (set)",
            "Occasion": "Diwali, pooja, home décor",
        },
        "meesho": {"Variation": "Free Size", "Type": "Diyas", "Color": "Gold", "Material": "Brass",
                   "Generic Name": "Diyas & Lanterns", "Net Quantity (N)": "2", "HSN ID": "741810", "GST %": "5"},
        "description": "Brass oil lamps with a heavy base for daily aarti and festive decor",
    },
    {
        "sku": "BRS-221", "name": "Brass akhand diya with borosilicate glass chimney", "category": "Pooja items",
        "mrp": 1299, "price": 999, "stock": 85,
        "attributes": {
            MEESHO_CATEGORY_ATTR: "13323", "Material": "Brass with borosilicate glass chimney",
            "Dimensions": "5 x 5 x 6.5 in", "Finish": "High gloss brass lacquer", "Weight": "500 g",
            "Occasion": "Daily pooja, Navratri, Akhand jyoti",
        },
        "meesho": {"Variation": "Free Size", "Type": "Diyas", "Color": "Gold", "Material": "Brass",
                   "Generic Name": "Diyas & Lanterns", "Net Quantity (N)": "1", "HSN ID": "741810", "GST %": "5"},
        "description": "Glass chimney shields the flame from wind",
    },
    {
        "sku": "BRS-222", "name": "Brass pooja thali set 7 pieces", "category": "Pooja items",
        "mrp": 2499, "price": 1899, "stock": 45,
        "attributes": {
            "Material": "Brass with Gayatri mantra engraving", "Dimensions": "9.5 in diameter plate",
            "Included": "Thali, Diya, Bell, Roli katori, Chawal katori, Dhoop stand, Spoon",
            "Finish": "Golden lustre", "Weight": "700 g",
        },
        "meesho": {"Variation": "Free Size", "Type": "Pooja Thalis & plates", "Color": "Gold", "Material": "Brass",
                   "Generic Name": "Puja Articles", "Net Quantity (N)": "1", "HSN ID": "741810", "GST %": "5",
                   "Product Length": "9.5", "Product Breadth": "9.5", "Product Height": "1", "Product Unit": "Inch"},
        "description": "Seven-piece pooja thali set for the home mandir and festive ceremonies",
    },
    {
        "sku": "BRS-223", "name": "Antique finish brass hanging peacock bell with chain", "category": "Pooja items",
        "mrp": 1599, "price": 1199, "stock": 60,
        "attributes": {
            "Material": "Cast brass", "Dimensions": "18 in total hang length (Bell 4 in)",
            "Finish": "Antique bronze patina", "Weight": "600 g", "Occasion": "Mandir entrance, balcony decor",
        },
        "meesho": {"Variation": "Free Size", "Type": "Pooja Bells", "Color": "Gold", "Material": "Brass",
                   "Generic Name": "Puja Articles", "Included Components": "1 bell with chain",
                   "Net Quantity (N)": "1", "HSN ID": "830610", "GST %": "18",
                   "Product Length": "4", "Product Breadth": "4", "Product Height": "18", "Product Unit": "Inch"},
        "description": "Peacock carving on the mounting hook",
    },
    {
        "sku": "BRS-224", "name": "Brass urli bowl with floating flower tealight holders", "category": "Pooja items",
        "mrp": 2199, "price": 1699, "stock": 40,
        "attributes": {
            "Material": "Solid brass", "Dimensions": "10 in diameter x 3.5 in depth",
            "Finish": "Hand-hammered gold finish", "Weight": "900 g",
            "Occasion": "Diwali, entrance rangoli, living room centrepiece",
        },
        "meesho": {"Variation": "Free Size", "Type": "Festive Bowl & Spoons", "Color": "Gold", "Material": "Brass",
                   "Generic Name": "Puja Articles", "Included Components": "1 urli bowl with tealight holders",
                   "Net Quantity (N)": "1", "HSN ID": "741810", "GST %": "5",
                   "Product Length": "10", "Product Breadth": "10", "Product Height": "3.5", "Product Unit": "Inch"},
        "description": "South Indian style urli for floating flowers and candles",
    },
    # Kurtas -> 10004 Kurtis; the men's kurta -> 10149 Men Kurtas
    {
        "sku": "KRT-310", "name": "Women's indigo dabu print straight kurta", "category": "Kurtas",
        "mrp": 1299, "price": 899, "stock": 65,
        "attributes": {
            "Material": "Cotton cambric", "Colour": "Indigo", "Print": "Dabu hand block print", "Fit": "Straight",
            "Sleeve": "3/4 sleeve", "Length": "46 in", "Size": "M (Bust 38 in)", "Care": "Hand wash cold",
        },
        "meesho": {"Variation": "M", "Color": "Navy Blue", "Combo of": "Single", "Fabric": "Cotton Cambric",
                   "Fit/ Shape": "Straight", "Generic Name": "Kurtis", "Length": "Calf Length", "Neck": "Round",
                   "Occasion": "Daily", "Pattern": "Printed", "Print or Pattern Type": "Block",
                   "Sleeve Length": "Three-Quarter Sleeves", "Stitch Type": "Stitched", "Bust Size": "38",
                   "Shoulder Size": "14.5", "Size Length": "46", "Waist Size": "34",
                   "HSN ID": "620442", "GST %": "5", "Net Weight (gms)": "250", "Net Quantity (N)": "1"},
        "description": "Mud-resist dabu print straight kurta with side slits",
    },
    {
        "sku": "KRT-311", "name": "Women's flared anarkali kurta in sanganeri block print", "category": "Kurtas",
        "mrp": 1999, "price": 1499, "stock": 42,
        "attributes": {
            "Material": "Mulmul cotton", "Colour": "Turquoise and peach", "Print": "Sanganeri floral jal print",
            "Fit": "Flared anarkali with tassels", "Sleeve": "Full sleeve", "Length": "48 in", "Size": "L (Bust 40 in)",
            "Care": "Dry clean or hand wash cold",
        },
        "meesho": {"Variation": "L", "Color": "Turquoise", "Combo of": "Single", "Fabric": "Mulmul",
                   "Fit/ Shape": "Anarkali", "Generic Name": "Kurtis", "Length": "Ankle Length", "Neck": "Round",
                   "Occasion": "Festive", "Pattern": "Printed", "Print or Pattern Type": "Floral",
                   "Sleeve Length": "Long Sleeves", "Stitch Type": "Stitched", "Bust Size": "40",
                   "Shoulder Size": "15", "Size Length": "48", "Waist Size": "36",
                   "HSN ID": "620442", "GST %": "5", "Net Weight (gms)": "300", "Net Quantity (N)": "1"},
        "description": "Tiered flared anarkali in light mulmul",
    },
    {
        "sku": "KRT-312", "name": "Men's short cotton kurta for casual and summer wear", "category": "Kurtas",
        "mrp": 1199, "price": 799, "stock": 55,
        "attributes": {
            MEESHO_CATEGORY_ATTR: "10149", "Material": "Slub cotton", "Colour": "Rust Orange", "Fit": "Regular fit",
            "Sleeve": "Long sleeve with roll-up tab", "Length": "30 in (hip length)", "Size": "L (Chest 40 in)",
            "Care": "Machine wash warm",
        },
        "meesho": {"Variation": "L", "Color": "Rust", "Combo of": "Single", "Fabric": "Cotton Slub",
                   "Generic Name": "Kurtas", "Length": "Thigh Length", "Neck": "Mandarin", "Occasion": "Daily",
                   "Pattern": "Solid", "Print or Pattern Type": "Solid", "Sleeve Length": "Long Sleeves",
                   "Stitch Type": "Stitched", "Type": "Regular", "Bust Size": "40", "Chest Size": "40",
                   "Length Size": "30", "HSN ID": "6211", "GST %": "5", "Net Weight (gms)": "220",
                   "Net Quantity (N)": "1"},
        "description": "Mandarin collar short kurta with a wooden button placket",
    },
    # Planters -> 13367
    {
        "sku": "BLU-415", "name": "Blue pottery ceramic planter with drainage hole", "category": "Planters",
        "mrp": 1299, "price": 1050, "stock": 25,
        "attributes": {
            "Material": "Hand-painted blue pottery ceramic", "Dimensions": "6 x 6 x 5.5 in", "Weight": "600 g",
            "Drainage": "Drainage hole with plug", "Colour": "Cobalt blue and white", "Use": "Indoor plants, succulents",
        },
        "meesho": {"Variation": "Free Size", "Add Ons": "No Add Ons", "Color": "Blue", "Generic Name": "Planter",
                   "Material": "Ceramic", "Net Quantity (N)": "Pack Of 1", "Shape": "Circular", "Type": "Indoor",
                   "HSN ID": "691200", "GST %": "18"},
        "description": "Glazed Jaipur blue pottery pot with geometric floral brushwork",
    },
    {
        "sku": "BLU-416", "name": "Ceramic succulent pot trio with bamboo tray", "category": "Planters",
        "mrp": 1599, "price": 1199, "stock": 35,
        "attributes": {
            "Material": "Glazed terracotta ceramic", "Dimensions": "3.5 x 3.5 in each pot, tray 11 x 4 in",
            "Weight": "800 g", "Drainage": "Yes, with drainage mesh", "Colour": "Pastel Sage, Ochre, and White",
            "Included": "3 ceramic pots + 1 natural bamboo tray",
        },
        "meesho": {"Variation": "Free Size", "Add Ons": "Tray", "Color": "Multicolor", "Generic Name": "Planter",
                   "Material": "Terracotta", "Net Quantity (N)": "Pack Of 3", "Shape": "Square", "Type": "Pot",
                   "HSN ID": "691200", "GST %": "18",
                   "Product Length": "11", "Product Breadth": "4", "Product Height": "3.5", "Product Unit": "Inch"},
        "description": "Tabletop planter trio for mini succulents and cacti",
    },
    # Ethnic footwear -> 12413 (men's) and 12435 (women's), set per product
    {
        "sku": "MJR-520", "name": "Men's handcrafted leather mojari with gold embroidery", "category": "Ethnic footwear",
        "mrp": 1999, "price": 1499, "stock": 30,
        "attributes": {
            MEESHO_CATEGORY_ATTR: "12413", "Upper": "Leather", "Sole": "Leather sole",
            "Colour": "Tan with gold embroidery", "Closure": "Slip-on", "Size": "UK 8", "Weight": "500 g",
            "Occasion": "Wedding and festive ethnic wear",
        },
        "meesho": {"Variation": "IND-8", "Color": "Brown", "Generic Name": "Mojaris and Juttis", "Material": "Leather",
                   "Pattern": "Embroidered", "Sole Material": "Leather", "Type": "Wedding", "Waterproof": "No",
                   "Foot Length Size": "26.5", "Foot Width Size": "10", "HSN ID": "64031990", "GST %": "5",
                   "Net Quantity (N)": "1"},
        "description": "Cushioned leather insole with Rajasthani zari thread detailing",
    },
    {
        "sku": "MJR-521", "name": "Women's mirror work and resham thread embroidery jutti", "category": "Ethnic footwear",
        "mrp": 1699, "price": 1299, "stock": 40,
        "attributes": {
            MEESHO_CATEGORY_ATTR: "12435", "Upper": "Raw silk with mirror work", "Sole": "Vegetable tanned leather",
            "Colour": "Rani Pink and Gold", "Closure": "Slip-on", "Size": "IND 6", "Insole": "Memory foam",
            "Weight": "400 g",
        },
        "meesho": {"Variation": "IND-6", "Color": "Pink", "Generic Name": "Juttis & Mojaris", "Heel Height": "Flat Heel",
                   "Insole": "Memory Foam", "Material": "Textile", "Occasion": "Wedding", "Pattern": "Embellished",
                   "Sole Material": "Leather", "Toe Type": "Pointed Toe", "Type": "Punjabi Jutti",
                   "Length Size": "24", "Width Size": "10", "HSN ID": "64059000", "GST %": "5",
                   "Net Quantity (N)": "1"},
        "description": "Double padded memory foam insole",
    },
    # Quilts -> 15875
    {
        "sku": "QLT-610", "name": "Jaipuri cotton razai, single bed light quilt", "category": "Quilts",
        "mrp": 2499, "price": 1899, "stock": 18,
        "attributes": {
            "Fill": "Cotton, 500 g", "Outer": "Cotton voile, hand block print", "Size": "Single, 60 x 90 in",
            "Weight": "500 g", "Colour": "Rose pink", "Care": "Dry clean recommended",
        },
        "meesho": {"Variation": "Single", "Color": "Pink", "Fabric": "Cotton", "Ideal Season": "Mild Winter",
                   "Thread Count": "100", "Type": "Quilt", "Product Height": "1", "HSN ID": "630130", "GST %": "5",
                   "Net Quantity (N)": "1"},
        "description": "Hand-carded cotton fill, quilted by hand in Jaipur",
    },
    {
        "sku": "QLT-611", "name": "Jaipuri double bed reversible cotton quilt", "category": "Quilts",
        "mrp": 3499, "price": 2699, "stock": 22,
        "attributes": {
            "Fill": "1000 g hand-carded cotton", "Outer": "Mulmul cotton", "Size": "Double, 90 x 100 in",
            "Weight": "1.2 kg", "Colour": "Royal Blue & Mustard reversible", "Care": "Dry clean only",
        },
        "meesho": {"Variation": "Double", "Color": "Blue", "Fabric": "Cotton", "Ideal Season": "Heavy Winter",
                   "Thread Count": "100", "Type": "Reversible Quilt", "Product Height": "1", "HSN ID": "630130",
                   "GST %": "5", "Net Quantity (N)": "1"},
        "description": "Reversible Mughal floral pattern with hand tagai stitching",
    },
]


def _product(p):
    """A seed product as the catalogue stores it: Meesho values as 'Meesho <column>' attributes."""
    p = dict(p)
    meesho = p.pop("meesho")
    return {
        **p,
        "brand": BRAND,
        "images": PRODUCT_IMAGES.get(p["sku"], []),
        "attributes": {**p["attributes"], **{f"{MEESHO_ATTR_PREFIX}{k}": v for k, v in meesho.items()}},
    }


PILOT_PRODUCTS = [_product(p) for p in _PRODUCTS]


def _replace_settings():
    SettingsService.update_seller_details(SELLER_DETAILS)
    for category, template_id in MEESHO_CATEGORY_DEFAULTS.items():
        if not MeeshoAdapter.template_by_ref(template_id):
            raise ValueError(f"Seed default for '{category}': {template_id} is not an official Meesho category")
        SettingsService.set_meesho_category_default(category, template_id)


def seed_database(replace: bool = False):
    check_connection()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        skus = [p["sku"] for p in PILOT_PRODUCTS]
        if replace:
            # Only these SKUs and their drafts; any other product is left alone
            ids = [pid for (pid,) in db.query(Product.id).filter(Product.sku.in_(skus)).all()]
            drafts = db.query(ListingDraft).filter(ListingDraft.product_id.in_(ids)).delete(synchronize_session=False) if ids else 0
            products = db.query(Product).filter(Product.id.in_(ids)).delete(synchronize_session=False) if ids else 0
            db.commit()
            print(f"[Seed] Removed {products} seed products and {drafts} drafts.", flush=True)
            _replace_settings()
            print("[Seed] Set Seller Details and Meesho category defaults.", flush=True)
        # The database is the source of truth: only add SKUs that don't exist, never overwrite them
        missing = [p for p in PILOT_PRODUCTS if not CatalogueService.get_by_sku(db, p["sku"])]
        created, _ = CatalogueService.batch_upsert_products(db, missing)
        print(f"[Seed] Seeding completed: {created} products created, {len(PILOT_PRODUCTS) - len(missing)} already present (left unchanged).", flush=True)
        without_photos = [p["sku"] for p in PILOT_PRODUCTS if not p["images"]]
        if without_photos:
            print(f"[Seed] No photos yet for {len(without_photos)} product(s); add their links to PRODUCT_IMAGES.", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    seed_database(replace="--replace" in sys.argv[1:])
