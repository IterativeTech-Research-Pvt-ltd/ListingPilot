import os
import sys
import openpyxl

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.database import SessionLocal, engine, Base, check_connection
from app.models.product import Product
from app.services.catalogue_service import CatalogueService

PILOT_PRODUCTS = [
    # Bedsheets (10 SKUs)
    {
        "sku": "JBP-101",
        "name": "Hand block print double bedsheet with 2 pillow covers",
        "category": "Bedsheets",
        "brand": "Gulmohar Home",
        "mrp": 1699,
        "price": 1299,
        "stock": 40,
        "images": [
            "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af",
            "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2",
            "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace",
            "https://images.unsplash.com/photo-1578683010236-d716f9a3f461",
            "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85"
        ],
        "attributes": {
            "Material": "100% cotton",
            "Size": "90 x 100 in (double)",
            "Thread count": "180 TC",
            "Colour": "Indigo and white",
            "Pattern": "Floral, hand block print",
            "Included": "1 bedsheet + 2 pillow covers (17 x 27 in)",
            "Care": "Machine wash cold"
        },
        "description": "Traditional Sanganeri hand block printed on 100% breathable cotton",
        "current_listing": {
            "title": "Bedsheet cotton double",
            "bullets": ["Good quality bedsheet", "Cotton"],
            "filled": 2,
            "flags": []
        }
    },
    {
        "sku": "JBP-102",
        "name": "Jaipuri Mughal motif king bedsheet with 2 pillow covers",
        "category": "Bedsheets",
        "brand": "Gulmohar Home",
        "mrp": 1999,
        "price": 1599,
        "stock": 25,
        "images": ["https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af", "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2", "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace"],
        "attributes": {
            "Material": "100% pure combed cotton",
            "Size": "108 x 108 in (king)",
            "Thread count": "210 TC",
            "Colour": "Maroon and Beige",
            "Pattern": "Mughal floral buti print",
            "Included": "1 King Bedsheet + 2 Pillow Shams (18 x 28 in)",
            "Care": "Gentle machine wash cold"
        },
        "description": "Rich regal Mughal buti hand block printed bedsheet for king mattresses"
    },
    {
        "sku": "JBP-103",
        "name": "Bagru natural dye block print double bedsheet",
        "category": "Bedsheets",
        "brand": "Gulmohar Home",
        "mrp": 1799,
        "price": 1399,
        "stock": 35,
        "images": ["https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af", "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2", "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace"],
        "attributes": {
            "Material": "100% organic cotton",
            "Size": "90 x 100 in (double)",
            "Thread count": "180 TC",
            "Colour": "Mustard and Black",
            "Pattern": "Geometric Bagru hand block print",
            "Included": "1 Double Sheet + 2 Pillow Covers",
            "Care": "Hand wash recommended for first 2 washes"
        },
        "description": "Crafted with vegetable and plant-based natural dyes in Bagru"
    },
    {
        "sku": "JBP-104",
        "name": "Pastel lotus print single bedsheet with 1 pillow cover",
        "category": "Bedsheets",
        "brand": "Gulmohar Home",
        "mrp": 1099,
        "price": 799,
        "stock": 50,
        "images": ["https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af", "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2"],
        "attributes": {
            "Material": "Cotton",
            "Size": "60 x 90 in (single)",
            "Thread count": "160 TC",
            "Colour": "Sage Green and Pink",
            "Pattern": "Lotus floral motif",
            "Included": "1 Single Bedsheet + 1 Pillow Cover",
            "Care": "Machine wash cold"
        },
        "description": "Delicate pastel lotus print ideal for single beds and kids bedrooms"
    },
    {
        "sku": "JBP-105",
        "name": "Indigo dabu print fitted double bedsheet with elastic",
        "category": "Bedsheets",
        "brand": "Gulmohar Home",
        "mrp": 1899,
        "price": 1499,
        "stock": 30,
        "images": ["https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af", "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2", "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace"],
        "attributes": {
            "Material": "100% cotton",
            "Size": "72 x 78 in + 10 in drop (fitted double)",
            "Thread count": "200 TC",
            "Colour": "Deep Indigo",
            "Pattern": "Dabu mud-resist geometric block print",
            "Included": "1 Fitted Sheet + 2 Pillow Covers",
            "Care": "Machine wash cold separately"
        },
        "description": "All-around elastic fitted sheet that stays tucked on thick mattresses"
    },

    # Pooja Items / Brassware (10 SKUs)
    {
        "sku": "BRS-220",
        "name": "Solid brass diya, set of 2",
        "category": "Pooja items",
        "brand": "Gulmohar Home",
        "mrp": 999,
        "price": 749,
        "stock": 120,
        "images": [
            "https://images.unsplash.com/photo-1605371924599-2d0365da1ae0",
            "https://images.unsplash.com/photo-1609137144813-7d9921338f24",
            "https://images.unsplash.com/photo-1514517521153-1be72277b32f"
        ],
        "attributes": {
            "Material": "Solid brass",
            "Dimensions": "4 x 4 x 2.5 in each",
            "Count": "Set of 2",
            "Finish": "Hand-polished antique gold",
            "Weight": "350 g (set)",
            "Occasion": "Diwali, pooja, home décor"
        },
        "description": "Heavy brass base oil lamps designed for stable daily aarti and festive decor",
        "current_listing": {
            "title": "Brass Diya",
            "bullets": ["brass diya for pooja"],
            "filled": 1,
            "flags": []
        }
    },
    {
        "sku": "BRS-221",
        "name": "Brass akhand diya with borosilicate glass chimney",
        "category": "Pooja items",
        "brand": "Gulmohar Home",
        "mrp": 1299,
        "price": 999,
        "stock": 85,
        "images": ["https://images.unsplash.com/photo-1605371924599-2d0365da1ae0", "https://images.unsplash.com/photo-1609137144813-7d9921338f24", "https://images.unsplash.com/photo-1514517521153-1be72277b32f"],
        "attributes": {
            "Material": "Solid virgin brass & thermal glass",
            "Dimensions": "5 x 5 x 6.5 in",
            "Finish": "High gloss brass lacquer",
            "Weight": "480 g",
            "Occasion": "Daily pooja, Navratri, Akhand jyoti"
        },
        "description": "Wind-resistant glass protector keeps flame burning steady for hours"
    },
    {
        "sku": "BRS-222",
        "name": "Handcrafted brass pooja thali set 7 pieces",
        "category": "Pooja items",
        "brand": "Gulmohar Home",
        "mrp": 2499,
        "price": 1899,
        "stock": 45,
        "images": ["https://images.unsplash.com/photo-1605371924599-2d0365da1ae0", "https://images.unsplash.com/photo-1609137144813-7d9921338f24", "https://images.unsplash.com/photo-1514517521153-1be72277b32f"],
        "attributes": {
            "Material": "Pure brass with Gayatri mantra engraving",
            "Dimensions": "9.5 in diameter plate",
            "Included": "Thali, Diya, Bell, Roli katori, Chawal katori, Dhoop stand, Spoon",
            "Finish": "Golden lustre",
            "Weight": "720 g"
        },
        "description": "Complete 7-piece pooja thali set for home mandir and festive ceremonies"
    },
    {
        "sku": "BRS-223",
        "name": "Antique finish brass hanging peacock bell with chain",
        "category": "Pooja items",
        "brand": "Gulmohar Home",
        "mrp": 1599,
        "price": 1199,
        "stock": 60,
        "images": ["https://images.unsplash.com/photo-1605371924599-2d0365da1ae0", "https://images.unsplash.com/photo-1609137144813-7d9921338f24"],
        "attributes": {
            "Material": "Cast brass",
            "Dimensions": "18 in total hang length (Bell 4 in)",
            "Finish": "Antique bronze patina",
            "Weight": "550 g",
            "Occasion": "Mandir entrance, balcony decor"
        },
        "description": "Resonant bell tone with detailed peacock carving on mounting hook"
    },
    {
        "sku": "BRS-224",
        "name": "Brass urli bowl with floating flower tealight holders 10 inch",
        "category": "Pooja items",
        "brand": "Gulmohar Home",
        "mrp": 2199,
        "price": 1699,
        "stock": 40,
        "images": ["https://images.unsplash.com/photo-1605371924599-2d0365da1ae0", "https://images.unsplash.com/photo-1609137144813-7d9921338f24", "https://images.unsplash.com/photo-1514517521153-1be72277b32f"],
        "attributes": {
            "Material": "Solid brass",
            "Dimensions": "10 in diameter x 3.5 in depth",
            "Finish": "Hand-hammered gold finish",
            "Weight": "850 g",
            "Occasion": "Diwali, entrance rangoli, living room centrepiece"
        },
        "description": "Traditional South Indian style Urli for floating fresh flowers and candles"
    },

    # Kurtas & Apparel (10 SKUs)
    {
        "sku": "KRT-310",
        "name": "Women's indigo dabu print straight kurta",
        "category": "Kurtas",
        "brand": "Gulmohar Home",
        "mrp": 1299,
        "price": 899,
        "stock": 65,
        "images": [
            "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b",
            "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1",
            "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f",
            "https://images.unsplash.com/photo-1539109136881-3be0616acf4b",
            "https://images.unsplash.com/photo-1509631179647-0177331693ae",
            "https://images.unsplash.com/photo-1490481651871-ab68de25d43d"
        ],
        "attributes": {
            "Material": "Cotton cambric",
            "Colour": "Indigo",
            "Print": "Dabu hand block print",
            "Fit": "Straight",
            "Sleeve": "3/4 sleeve",
            "Length": "46 in",
            "Size": "M (Bust 38 in)",
            "Care": "Hand wash cold"
        },
        "description": "Natural dye mud-resist dabu print straight kurta with side slits",
        "current_listing": {
            "title": "Kurta for women cotton printed",
            "bullets": ["Cotton kurta", "Free delivery"],
            "filled": 3,
            "flags": ["Mentions “Free delivery”, which Amazon does not allow in listing text"]
        }
    },
    {
        "sku": "KRT-311",
        "name": "Women's flared anarkali kurta in sanganeri block print",
        "category": "Kurtas",
        "brand": "Gulmohar Home",
        "mrp": 1999,
        "price": 1499,
        "stock": 42,
        "images": ["https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b", "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1", "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f"],
        "attributes": {
            "Material": "100% fine mulmul cotton",
            "Colour": "Turquoise and peach",
            "Print": "Sanganeri floral jal print",
            "Fit": "Flared anarkali with tassels",
            "Sleeve": "Full sleeve",
            "Length": "48 in",
            "Care": "Dry clean or hand wash cold"
        },
        "description": "Tiered flared silhouette crafted from featherlight breathable mulmul"
    },
    {
        "sku": "KRT-312",
        "name": "Men's short cotton kurta for casual and summer wear",
        "category": "Kurtas",
        "brand": "Gulmohar Home",
        "mrp": 1199,
        "price": 799,
        "stock": 55,
        "images": ["https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b", "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1", "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f"],
        "attributes": {
            "Material": "Slub cotton",
            "Colour": "Rust Orange",
            "Fit": "Regular fit",
            "Sleeve": "Long sleeve with roll-up tab",
            "Length": "30 in (hip length)",
            "Care": "Machine wash warm"
        },
        "description": "Mandarin collar short kurta with wooden button placket"
    },

    # Ceramic Planters & Pottery (10 SKUs)
    {
        "sku": "BLU-415",
        "name": "Blue pottery ceramic planter 6 inch with drainage hole",
        "category": "Planters",
        "brand": "Gulmohar Home",
        "mrp": 1299,
        "price": 1050,
        "stock": 25,
        "images": [
            "https://images.unsplash.com/photo-1485955900006-10f4d324d411",
            "https://images.unsplash.com/photo-1512496015851-a90fb38ba796"
        ],
        "attributes": {
            "Material": "Hand-painted blue pottery ceramic",
            "Dimensions": "6 x 6 x 5.5 in",
            "Drainage": "Drainage hole with plug",
            "Colour": "Cobalt blue and white",
            "Use": "Indoor plants, succulents"
        },
        "description": "Glazed quartz-based Jaipur blue pottery pot with geometric floral brushwork",
        "current_listing": {
            "title": "Planter",
            "bullets": [],
            "filled": 1,
            "flags": []
        }
    },
    {
        "sku": "BLU-416",
        "name": "Handmade ceramic succulent pot trio with bamboo tray",
        "category": "Planters",
        "brand": "Gulmohar Home",
        "mrp": 1599,
        "price": 1199,
        "stock": 35,
        "images": ["https://images.unsplash.com/photo-1485955900006-10f4d324d411", "https://images.unsplash.com/photo-1512496015851-a90fb38ba796", "https://images.unsplash.com/photo-1509423350716-97f9360b4e09"],
        "attributes": {
            "Material": "Glazed terracotta ceramic",
            "Dimensions": "3.5 x 3.5 in each pot, tray 11 x 4 in",
            "Drainage": "Yes, with drainage mesh",
            "Colour": "Pastel Sage, Ochre, and White",
            "Included": "3 ceramic pots + 1 natural bamboo tray"
        },
        "description": "Tabletop windowsill planter trio designed for mini succulents and cacti"
    },

    # Ethnic Footwear / Mojaris (10 SKUs)
    {
        "sku": "MJR-520",
        "name": "Men's handcrafted genuine leather mojari with gold embroidery",
        "category": "Ethnic footwear",
        "brand": "Gulmohar Home",
        "mrp": 1999,
        "price": 1499,
        "stock": 30,
        "images": [
            "https://images.unsplash.com/photo-1549298916-b41d501d3772",
            "https://images.unsplash.com/photo-1560769629-975ec94e6a86",
            "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77",
            "https://images.unsplash.com/photo-1608256246200-53e635b5b65f",
            "https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a"
        ],
        "attributes": {
            "Upper": "Genuine leather",
            "Sole": "Leather sole",
            "Colour": "Tan with gold embroidery",
            "Closure": "Slip-on",
            "Sizes": "UK 6 to 11",
            "Occasion": "Wedding and festive ethnic wear"
        },
        "description": "Cushioned leather insole with handcrafted Rajasthani zari thread detailing",
        "current_listing": {
            "title": "Mojari men",
            "bullets": ["Leather", "Wedding wear"],
            "filled": 2,
            "flags": []
        }
    },
    {
        "sku": "MJR-521",
        "name": "Women's mirror work and resham thread embroidery jutti",
        "category": "Ethnic footwear",
        "brand": "Gulmohar Home",
        "mrp": 1699,
        "price": 1299,
        "stock": 40,
        "images": ["https://images.unsplash.com/photo-1549298916-b41d501d3772", "https://images.unsplash.com/photo-1560769629-975ec94e6a86", "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77"],
        "attributes": {
            "Upper": "Raw silk with genuine mirror work",
            "Sole": "Vegetable tanned leather",
            "Colour": "Rani Pink and Gold",
            "Closure": "Slip-on with double cushioning",
            "Sizes": "IND 4 to 8"
        },
        "description": "Double padded memory foam insole prevents shoe bites during ceremonies"
    },

    # Quilts / Razais (10 SKUs)
    {
        "sku": "QLT-610",
        "name": "Jaipuri cotton razai, single bed ultra-light quilt",
        "category": "Quilts",
        "brand": "Gulmohar Home",
        "mrp": 2499,
        "price": 1899,
        "stock": 18,
        "images": [
            "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2",
            "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af",
            "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace",
            "https://images.unsplash.com/photo-1578683010236-d716f9a3f461",
            "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85"
        ],
        "attributes": {
            "Fill": "Cotton, 500 g",
            "Outer": "Cotton voile, hand block print",
            "Size": "Single, 60 x 90 in",
            "Weight": "Ultra-light, 500 g",
            "Colour": "Rose pink",
            "Care": "Dry clean recommended"
        },
        "description": "Hand-carded natural cotton fill quilted by hand in Jaipur for featherweight warmth",
        "current_listing": {
            "title": "Jaipuri Razai single bed light weight",
            "bullets": ["Light weight razai", "Cotton"],
            "filled": 3,
            "flags": []
        }
    },
    {
        "sku": "QLT-611",
        "name": "Jaipuri double bed reversible cotton quilt 90 x 108 inch",
        "category": "Quilts",
        "brand": "Gulmohar Home",
        "mrp": 3499,
        "price": 2699,
        "stock": 22,
        "images": ["https://images.unsplash.com/photo-1584100936595-c0654b55a2e2", "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af", "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace"],
        "attributes": {
            "Fill": "1000 g hand-carded cotton",
            "Outer": "100% fine mulmul cotton",
            "Size": "Double / King, 90 x 108 in",
            "Weight": "1.2 kg",
            "Colour": "Royal Blue & Mustard reversible",
            "Care": "Dry clean only"
        },
        "description": "Reversible Mughal floral pattern on both sides with fine hand tagai stitching"
    }
]

def seed_database():
    check_connection()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # The database is the source of truth: only add SKUs that don't exist, never overwrite them
        missing = [p for p in PILOT_PRODUCTS if not CatalogueService.get_by_sku(db, p["sku"])]
        created, _ = CatalogueService.batch_upsert_products(db, missing)
        print(f"Seeding completed: {created} products created, {len(PILOT_PRODUCTS) - len(missing)} already present (left unchanged).")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
