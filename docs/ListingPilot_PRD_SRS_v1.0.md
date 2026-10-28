# ListingPilot — Multi-Marketplace Listing Automation

## Product Requirements Document & Software Requirements Specification

|                  |                             |
| ---------------- | --------------------------- |
| **Version**      | 1.0 (consolidated)          |
| **Date**         | 28 October 2026             |
| **Status**       | Draft for review            |
| **Marketplaces** | Amazon.in, Flipkart, Meesho |

### Version history

| Version | Summary                                                                                            |
| ------- | -------------------------------------------------------------------------------------------------- |
| 0.1     | Initial PRD/SRS: platform research, Master Catalogue, AI content, adapters, requirements           |
| 0.2     | AI image generation, Meesho shipping-aware images, conditional/category-specific field engine      |
| 0.3     | Analysis of official Meesho templates (T-shirts, Shirts, Sneakers, Bedsheets); Meesho adapter spec |
| 0.4     | Decision to bundle Meesho templates in the codebase; seller uploads filled files manually          |
| 1.0     | Consolidated document (this file)                                                                  |

---

## Table of contents

1. Executive summary
2. Problem statement
3. Platform research
4. Goals, non-goals, personas, success metrics
5. Product principles
6. Scope and module overview
7. Master Catalogue data model
8. Product Flags and Conditional Rule Engine
9. AI content generation
10. AI image generation
11. Meesho Shipping Optimiser
12. Human-in-the-loop (manual) fields
13. Channel adapters and publishing
14. Meesho two-price model and returns advisor
15. Validation rules
16. Functional requirements
17. Non-functional requirements
18. Architecture and tech stack
19. Risks
20. Roadmap
21. Open questions and Phase 0 checklist
22. References

- Appendix A: Meesho template field inventory
- Appendix B: Glossary

---

## 1. Executive summary

Indian sellers listing on Amazon, Flipkart and Meesho maintain the same product three times, in three data models, under three sets of rules for titles, images, categories and compliance. Each platform rejects listings for different reasons, and fixes made in one channel rarely flow back to the others.

ListingPilot solves this with a single **Master Catalogue** acting as the knowledge base for every product. Sellers (assisted by AI) enter product facts once. The system then:

- classifies each product into each platform's category,
- maps attributes to each platform's allowed values,
- generates platform-specific written content and images with AI,
- validates everything against each platform's rules,
- routes fields that cannot be safely automated to a human review queue, and
- publishes through the best channel available: the official API for Amazon, API or filled upload templates for Flipkart, and filled official upload templates for Meesho (uploaded manually by the seller).

**Core principle: facts in the master, expression in the channel.** Facts (dimensions, material, MRP, country of origin, GTIN, compliance declarations) live only in the Master Catalogue and are never invented by AI. Expression (titles, bullets, descriptions, keywords, image compositions) is generated per platform from those facts.

---

## 2. Problem statement

- **Triple data entry.** The same product must be entered in Amazon's JSON schema / flat files, Flipkart's vertical templates and Meesho's category templates.
- **Divergent rules.** Title limits, image rules, mandatory attributes and variant models differ per platform and change frequently (e.g., Amazon's 75-character title limit from 27 July 2026).
- **Opaque rejections.** Flipkart and Meesho QC messages are often generic; sellers iterate blindly.
- **Compliance burden.** Legal Metrology declarations, BIS/QCO marks, and tax data must be accurate on every listing on every platform.
- **Economics hidden in listing data.** On Meesho, shipping cost (driven by weight and possibly image-derived size estimates) and return policy pricing directly determine margin.
- **No single source of truth.** Fixes made on one channel drift from others.

---

## 3. Platform research

### 3.1 Amazon (amazon.in)

**Integration path: full public API (Selling Partner API).**

- The **Listings Items API** manages product facts (e.g., title) and sales terms (price, inventory). Payloads follow JSON Schemas served by the **Product Type Definitions API**, which can be fetched per product type and used to validate data before submission.
- **Bulk:** the `JSON_LISTINGS_FEED` feed type is the bulk equivalent with the same schemas.
- **Schema freshness:** cache schemas and refresh on `PRODUCT_TYPE_DEFINITIONS_CHANGE` notifications.
- **Two listing flows:** (1) new product → fetch schema → validate locally → `putListingsItem`; (2) existing ASIN → search catalog by GTIN/keywords → offer-only listing using the `PRODUCT` product type with the offer-only requirement set. Always search first to avoid duplicate ASINs.
- **Conditional logic** is encoded in the schemas (JSON Schema 2019-09 plus Amazon's meta-schema vocabulary). Passing a seller ID returns seller-specific values (e.g., approved brands). A non-enforced mode validates attributes individually for partial updates. The API also returns recommended browse nodes and item-type keywords.
- **Rate limits:** `putListingsItem` ≈ 5 requests/second per account (burst 5); use feeds for bulk.

**Content rules (2026):**

- **Title ≤ 75 characters** (including spaces) in all categories except media, effective 27 July 2026. Non-compliant titles are gradually replaced by Amazon's AI-generated recommendation; listings stay active.
- **Item Highlights:** a new 125-character searchable field shown below the title, available once the title is ≤ 75 characters. Amazon states title and highlights are both search inputs with equal priority.
- **Bullets:** typically 5.
- **Backend search terms:** < 200 bytes in India; no brand names (including own), no repetition of title/bullet content, no non-descriptive terms.

**Images:**

- Main image: pure white background (RGB 255,255,255), product fills ≥ 85% of frame, no added text/graphics/watermarks, no props not included, real product (not illustration), ≥ 1000 px on longest side for zoom.
- Off-white backgrounds (e.g., #FAFAFA) fail automated checks.
- AI: main image must depict the real product; AI edits starting from a real photo are generally accepted; fully synthetic renders are risky. AI-generated human models (fashion) are a policy grey zone. Lifestyle/AI composites belong in secondary slots only.

**Identifiers:** GS1 India is the only authorised source of UPC/EAN accepted. Alternatives: GTIN exemption or Brand Registry. The API does not reveal to third parties whether a seller holds an exemption → must be seller-declared.

**Variations:** non-buyable parent, children with unique IDs, a valid variation theme per product type (e.g., SizeColor requires size, size_map, color_name, color_map); product type must match across family; the variation theme cannot be changed after the parent is created.

**Dangerous goods / batteries:** `batteries_required` (internal rechargeable batteries count) triggers battery and DG attributes; Amazon recommends supplying DG info even for non-regulated products.

### 3.2 Flipkart

**Integration path: API for offers on existing catalog products; Excel templates via Seller Hub for new products.**

- **Listing Management API v3** (`POST /listings/v3`, `/listings/v3/update`) creates/updates listings: price (MRP, selling price), tax (HSN, tax code such as `GST_APPAREL`), fulfillment (dispatch SLA, shipping provider, procurement type), packages, locations, Legal Metrology address labels.
- Requires `product_id` = **FSN** (13–16 chars) → the API attaches offers to products already in Flipkart's catalog. Creating a listing for an existing SKU **overwrites** it.
- API access is not automatic on seller registration.
- **New products:** Seller Hub → Add New Listing → select vertical and brand → download template → fill → upload → QC.
- **Brand approval** required for many brands/verticals (trademark, authorisation letter, invoices, licences).
- **Variants** must be created in the catalog sheet at the outset; Flipkart does not allow adding variants to an existing product. Attributes cannot be added after verification without seller support.
- **Template tiers:** mandatory, conditionally mandatory, product-specific mandatory, good-to-have. Attribute sets vary heavily by vertical (apparel: fabric, fit, occasion, sleeve length, pattern, wash care). Electronics, beauty and certified categories have extra gating.
- **Not allowed:** customisable products and assorted products.
- **Images:** white/light-grey background (white for primary), no price tags, stickers, text or watermarks. QC feedback is often generic.

### 3.3 Meesho

**Integration path: no public listing API. Official Excel templates uploaded via the Supplier Panel.**

- Meesho's seller API is private, offered to OMS/ERP partners (EasyEcom, Unicommerce, Vinculum) mainly for orders, inventory, payments and returns; SKUs must already exist in the panel.
- Bulk flow: Catalog Upload → Add Bulk Catalog → select category → download template → fill → upload → validation → QC → live (third-party sources cite ~72 hours).
- A **catalog** is a group of products of a single category (grouped via Group ID); 3–4+ products per catalog recommended.
- **Economics:** 0% commission; shipping is system-calculated by weight slab and zone and cannot be edited by sellers; returns (RTO) are the main cost.

**Findings from official templates (T-shirts 10000, Shirts 10001, Bedsheets 10058, Sneakers 13178):**

- Explicit text markers per column: `* Compulsory Field` / `Optional Field`.
- **4 image slots** per SKU; Image 1 (Front) compulsory. **JPEG only, RGB only.** Image links must be generated via the Supplier Panel image uploader (no Google Drive links).
- **Pre-packed products:** Image 1 (packaging front) and Image 2 (packaging back) mandatory, showing legally required label information; all four sides recommended.
- **QCO products:** clear photo of ISI mark and registration number; CM/L and IS Number fields (e.g., footwear).
- **Rejected images:** graphic/inverted/pixelated/duplicate, text or watermark on primary, blur/clutter, price or brand logo, shrunk/elongated/stretched products, partial products, offensive content.
- **Restricted keywords:** smoking references, other portal names, violent slogans. Product Name must not contain weight, dimensions or price.
- **Two-price model:** Meesho Price (all return reasons allowed) + optional Wrong/Defective Return Discount in ₹ (buyers paying the lower price can return only for wrong/defective reasons). Template recommends ₹22. Rules: Meesho Price < MRP; Wrong/Defective price < Meesho Price.
- **No packed weight or package dimension field.** Only Net Weight (product, excluding packaging). Meesho must estimate packaging by other means.
- **ERROR STATUS / ERROR MESSAGE** columns are filled by Meesho on processed files.
- **Hidden fingerprint** in the Instructions sheet (e.g., `10000 | 51 | BASE | pre_tp_experiment`): category ID, version, type, experiment flag → Meesho appears to A/B test templates.
- **Category paths matter:** the bedsheet template is under _Kids & Toys / Accessories / Unisex / Bedsheets_.
- **Dropdown values include typos** that must be preserved exactly (e.g., "Lavendar", "Fuchisa", "Syntethic Leather", "Abstrast", "Not Available]").
- **Brand:** closed dropdown of approved brands + free-text Brand Name; both optional.
- **Licensed characters:** T-shirt template has a Character dropdown (Avengers, Mickey Mouse, etc.).
- Meesho's own example rows contain errors (MRP = 0; SKU suffix not matching size).

**Meesho image rules beyond templates** are kept inside the logged-in panel; ListingPilot ships them as admin-editable rules.

### 3.4 Cross-platform Indian compliance

- **Legal Metrology (Packaged Commodities) Rules, 2011** (as amended for e-commerce): listings must show mandatory declarations including manufacturer/packer/importer name and address, country of origin, net quantity, MRP, customer care details, and generic name. Both sellers and platforms can face action (Amazon has been penalised for missing country of origin).
- **BIS / Quality Control Orders:** ISI mark and licence numbers for covered products.
- **FSSAI** for food, **CDSCO**-related requirements for certain cosmetics/medical items.
- **GST:** HSN and rate must be consistent; some categories have price-dependent rates (admin-maintained, tax-advisor verified).

### 3.5 Research summary matrix

| Dimension                 | Amazon                                | Flipkart                         | Meesho                                      |
| ------------------------- | ------------------------------------- | -------------------------------- | ------------------------------------------- |
| Listing creation          | Public API + JSON feeds               | API (existing FSN) / Excel (new) | Excel via Supplier Panel only               |
| Schema source             | JSON Schema per product type          | Per-vertical Excel template      | Per-category Excel template                 |
| Product unit              | ASIN (parent/child)                   | FSN (variants by style code)     | Catalog (Group ID) of SKUs                  |
| Title rule                | ≤ 75 chars + 125-char Item Highlights | Template-driven                  | No weight/dimension/price in name           |
| Gate                      | GTIN / exemption / Brand Registry     | Brand approval                   | GSTIN or Enrolment ID; brand dropdown       |
| Top rejection drivers     | Images, GTIN, variations              | Opaque QC, brand approval        | QC, images, duplicates, dropdown mismatches |
| Est. automation ceiling\* | ~90%                                  | ~60–70%                          | ~55% (file generation; upload manual)       |

\*Planning estimates, not sourced figures.

---

## 4. Goals, non-goals, personas, success metrics

### 4.1 Goals

- Enter a product once; get compliant, high-quality listings on all three platforms with minimal rework.
- Reduce time-to-list per SKU (3 channels) from hours to minutes.
- Cut first-submission rejection rates through pre-validation.
- Keep channels in sync from one source of truth.
- Make the few seller-only decisions explicit and easy.

### 4.2 Non-goals (v1)

- Order management, multi-warehouse inventory sync, repricing, ads, returns handling, accounting (integrate with OMS tools later).
- Browser automation / RPA of Flipkart or Meesho seller panels (ToS risk).
- Additional marketplaces (Myntra, Ajio, JioMart, ONDC) — deferred to v2; architecture must support them.

### 4.3 Personas

| Persona                                | Profile                                              | Key pain                                     |
| -------------------------------------- | ---------------------------------------------------- | -------------------------------------------- |
| Small D2C brand owner (primary)        | 50–500 SKUs; fashion, home, beauty; lists personally | Rewriting for 3 platforms; opaque rejections |
| Catalogue ops executive (primary)      | 1,000–20,000 SKUs at a brand/agency                  | Template hell; version drift; bulk fixes     |
| Agency manager (secondary)             | Multiple client brands                               | Multi-tenant workspaces, approvals, audit    |
| Meesho reseller/wholesaler (secondary) | Low price points, high churn, minimal photography    | Speed, image cleanup, shipping cost          |

### 4.4 Success metrics (6 months post-launch)

| Metric                                                        | Target                  |
| ------------------------------------------------------------- | ----------------------- |
| Median time from master creation to "ready" on all 3 channels | < 10 min/SKU            |
| Amazon first-submission acceptance                            | ≥ 90%                   |
| Flipkart/Meesho first-upload acceptance                       | ≥ 80%                   |
| AI-written fields accepted without edit                       | ≥ 70%                   |
| AI factual-error rate (audit sample)                          | < 1%                    |
| Sellers publishing to ≥ 2 channels weekly                     | Leading adoption metric |

---

## 5. Product principles

1. **Facts in the master, expression in the channel.** AI never invents facts.
2. **Rules are data, not code.** Limits and requirements come from Amazon schemas, compiled templates and admin rule sets.
3. **Deterministic validation wraps AI.** Code checks every AI output before a human or platform sees it.
4. **Real product, real photos.** AI images are anchored to seller photos; product pixels are locked.
5. **Seller accounts are sacred.** Only official APIs and seller-performed uploads; no panel automation.
6. **Honest optimisation.** Shipping and pricing optimisations never misrepresent the product or under-declare weight/dimensions.
7. **Human-only for legal, safety and money decisions.**

---

## 6. Scope and module overview

| #   | Module                                  | Purpose                                                                                                             |
| --- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 1   | Master Catalogue                        | Canonical product, variant, media, compliance, logistics and pricing data                                           |
| 2   | Ingestion                               | Forms, CSV/XLSX import, Amazon listing import, Flipkart/Meesho export import, AI extraction from photos/spec sheets |
| 3   | Taxonomy & Mapping                      | Category classification per channel; attribute value mapping                                                        |
| 4   | Product Flags & Conditional Rule Engine | One-time real-world flags driving channel requirements; dynamic forms                                               |
| 5   | AI Content Studio                       | Titles, highlights, bullets, descriptions, keywords per channel                                                     |
| 6   | Media Studio                            | Image QC, cleanup, AI composites, infographics, channel derivatives                                                 |
| 7   | Meesho Shipping Optimiser               | Slab analysis, packaging advice, compliant presentation variants, test recording                                    |
| 8   | Validation Engine                       | Per-channel readiness scoring, blocking rules                                                                       |
| 9   | Review & Task Queue                     | Human-in-the-loop decisions and approvals                                                                           |
| 10  | Channel Adapters                        | Amazon API/feeds; Flipkart API/templates; Meesho bundled template library                                           |
| 11  | Status, Feedback & Sync                 | Error ingestion, error dictionaries, change propagation                                                             |

---

## 7. Master Catalogue data model

### 7.1 Core entities

| Entity                       | Purpose                          | Key fields                                                                                                                                                                                  |
| ---------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ProductFamily                | Style/design shared by variants  | family_id, brand_id, internal_name, master_category, variation_theme, base_facts, meesho_template_id (confirmed)                                                                            |
| Variant                      | Sellable SKU                     | sku, family_id, variant_attributes, GTIN, gtin_status (GS1/exempt/none), HSN, GST rate, MRP, cost, status                                                                                   |
| AttributeValue               | Typed, normalised facts          | entity_id, attribute_key, value, unit, source (manual/AI/import), confidence, verified_by, verified_at                                                                                      |
| ComplianceBlock              | Legal Metrology + certifications | manufacturer/packer/importer name, address, pincode; country of origin; net quantity + unit; MRP; customer care; BIS/CM-L/IS no.; FSSAI; licence docs + expiry                              |
| Logistics / PackagingProfile | Shipping-critical                | net weight, packed weight, packed L×B×H, volumetric weight, slab estimate, packaging type, verified                                                                                         |
| SizeChart                    | Per-family size measurements     | size_label, measurements {chest, length, shoulder, foot_length, foot_width, …}, unit, source, verified_by                                                                                   |
| ProductFlag                  | Real-world toggles               | flag_key, value, suggested_by_ai, confirmed_by, confirmed_at                                                                                                                                |
| Brand                        | Brand gating                     | name, trademark no., Amazon Brand Registry, Amazon GTIN-exempt categories, Flipkart approval per vertical, Meesho dropdown presence, documents                                              |
| MediaAsset                   | Images/videos                    | origin (seller_photo/ai_edit/ai_composite/ai_inferred_view/ai_recolour), sot_parent_id, role, variant_ids, generation_params, fidelity_scores, allowed_channels, allowed_slots, approved_by |
| ContentVersion               | Generated copy                   | channel, field, text, prompt_version, model, grounding_fact_ids, status, editor                                                                                                             |
| ChannelListing               | Per variant per channel          | channel, channel_category, external IDs (ASIN, FSN/LID, Meesho IDs), status, last_payload, errors, live_url                                                                                 |
| PricingProfile               | Per-channel economics            | target margin, fee assumptions, shipping estimate, return assumptions, computed price                                                                                                       |
| MeeshoPricing                | Two-price model                  | meesho_price, wd_discount, computed_wd_price, rationale                                                                                                                                     |
| ShippingTest                 | Meesho shipping experiments      | variant_id, image_asset_id, image_params, packed weight/dims, category, observed_charge, evidence, shared_anonymised                                                                        |
| ConditionalRule              | Channel requirements             | channel, scope, condition, required_fields, blocked_actions, source, source_version, verified_by                                                                                            |
| MeeshoTemplate               | Bundled template registry        | category_id, version, type, experiment_flag, variant, category_path, sheet_name, data_start_row, raw_file, sha256, downloaded_on, verified_on, status                                       |
| TemplateField                | Compiled template fields         | template_id, column, label, description, required, unit, allowed_values[], master_attribute_key                                                                                             |
| ExportBatch                  | Generated files                  | template_id, rows, file_ref, status (generated/uploaded/errors_imported/live), error_rows                                                                                                   |
| MeeshoErrorDictionary        | Learned rejection map            | message_pattern, field, fix_suggestion, occurrence_count                                                                                                                                    |

### 7.2 Design rules

- Every AttributeValue carries **provenance and confidence**; low-confidence AI values cannot publish until verified.
- A **master attribute dictionary** is the canonical vocabulary; per-channel mappings translate to channel enums. Confirmed mappings are reusable rules.
- ContentVersion and generated images reference the facts they rely on; changing a fact marks dependent content **stale**.
- Declared weights/dimensions are locked to verified master values.

---

## 8. Product Flags and Conditional Rule Engine

### 8.1 Problem

The same real-world question ("does it contain a battery?") appears as a schema conditional on Amazon, a vertical column on Flipkart, and a category choice on Meesho. Asking per platform breaks the master promise.

### 8.2 Product Flags (asked once; human-confirmed)

| Flag                                      | Drives                                                                         |
| ----------------------------------------- | ------------------------------------------------------------------------------ |
| Contains/requires batteries (+ chemistry) | Amazon battery & DG attributes; Flipkart battery fields; shipping restrictions |
| Liquid / aerosol / flammable / corrosive  | Hazmat classification                                                          |
| Expiry-dated                              | Shelf life, expiry fields, dating label                                        |
| Food                                      | FSSAI no., ingredients, veg/non-veg, nutrition                                 |
| Cosmetic / personal care                  | Ingredients, skin/hair type, regulatory fields                                 |
| Electrical / electronic                   | BIS no., warranty, model, wattage/voltage                                      |
| Imported                                  | Importer details; country of origin ≠ India                                    |
| Pre-packed                                | Packaging front/back images mandatory (Meesho); Legal Metrology label data     |
| QCO-covered                               | CM/L, IS number, ISI mark photo                                                |
| Licensed character                        | Licence document required before export                                        |
| Has variants (theme)                      | Variation theme per channel; child attributes                                  |
| Set / combo / multipack                   | Pack-of, item count, included components                                       |
| Customisable or assorted                  | **Blocks Flipkart export**                                                     |
| Age-restricted / adult                    | Gating, image restrictions                                                     |
| Wearable                                  | Size chart, size system, gender, age group                                     |
| Medical / health claim                    | Blocks AI health claims; evidence docs                                         |
| Multi-box shipment                        | Package count, per-box dimensions                                              |
| Fragile                                   | Packaging guidance                                                             |
| Warranty                                  | Type, duration, service details                                                |

AI may _suggest_ flags (e.g., visible USB port → possible battery); a human must confirm.

### 8.3 Conditional Rule Engine

Rules share one format, e.g.:

```
WHEN master.flags.contains_battery = true AND channel = amazon
THEN require [battery.cell_composition, battery.count, battery.type, supplier_declared_dg_hz_regulation]
SOURCE amazon_ptd:<product_type>@<schema_version>
```

Rule sources:

- **Amazon:** auto-compiled from product type schemas on every schema change.
- **Flipkart/Meesho:** compiled from templates (markers, dropdowns, instruction text); AI drafts conditions from instruction text, an admin verifies before go-live.
- **Admin rules:** knowledge not in any file (e.g., Flipkart ban on customisable products).

### 8.4 Progressive-disclosure forms

1. **Universal core:** identity, brand, compliance, logistics, flags.
2. **Category pack:** union of category attributes across channels, de-duplicated via the master dictionary.
3. **Channel deltas:** fields unique to one platform, with per-channel completeness meters.

Fields appear only when rule conditions are met. AI pre-fills layers 2–3 with confidence scores.

### 8.5 Change handling

Changing a flag or category triggers impact analysis: newly required fields, invalidated fields, and one-way-door warnings (Amazon variation theme; Flipkart variants).

---

## 9. AI content generation

### 9.1 Outputs

| Output                  | Amazon                         | Flipkart                | Meesho                                 | AI role                     |
| ----------------------- | ------------------------------ | ----------------------- | -------------------------------------- | --------------------------- |
| Title / Product Name    | ≤ 75 chars                     | Template                | No weight/dimension/price/portal names | Full generation             |
| Item Highlights         | ≤ 125 chars                    | —                       | —                                      | Full generation             |
| Bullets / key features  | ~5                             | Where template has them | —                                      | Full generation             |
| Description             | Long-form                      | Long-form               | 2–4 sentences                          | Full generation             |
| Backend keywords        | < 200 bytes                    | Where present           | —                                      | Generation + byte count     |
| Generic Name            | —                              | —                       | From template's allowed list           | Selection                   |
| Included Components     | —                              | —                       | e.g., "1 bedsheet, 2 pillow covers"    | From master list            |
| Category classification | Product type + browse node     | Vertical                | Template leaf                          | Suggestion + confidence     |
| Attribute value mapping | Schema enums                   | Dropdowns               | Exact dropdown strings                 | Suggestion; rules preferred |
| Attribute extraction    | Photos, spec sheets, packaging | same                    | same                                   | Extraction + confidence     |
| Error explanation       | Map to field + fix             | same                    | same                                   | Assistive                   |

### 9.2 Pipeline

1. **Fact assembly:** verified attributes, compliance block, base facts.
2. **Channel brief:** live constraints (schema/compiled template), brand voice, keywords.
3. **Constrained generation:** content plus fact IDs per sentence.
4. **Deterministic validation:** length, bytes, banned terms, cross-field duplication, fact coverage → auto-regenerate with the specific violation (N attempts) → human.

### 9.3 Guardrails

- No unsupported claims (material, dimensions, certifications, health, warranty, compatibility, performance).
- Banned terms: promotional ("best seller", "No.1"), competitor brands, offers/prices in content, health claims without evidence, other portal names (Meesho), restricted keywords (smoking, violent slogans).
- Amazon backend: no brand names, no repetition.
- Versioned; publish requires approval or opted-in auto-approve rules.

### 9.4 Amazon title strategy

Slot formula: Brand + core noun + top differentiator + key variant attribute (≤ 75 chars). Remaining search attributes go to Item Highlights. A ~150-char "long master title" also serves Flipkart and as input for highlights.

### 9.5 Language

English in v1; Hindi/regional in v2 with byte-aware checks.

---

## 10. AI image generation

### 10.1 Source of Truth (SoT) rule

- Every variant needs **≥ 1 seller-provided photograph** (SoT). Nothing publishes without it.
- Each colour needs its own SoT photo. AI recolouring only with explicit approval, labelled "AI colour preview", never on Amazon main, only secondary slots on Flipkart/Meesho.
- **Packaging photos (pre-packed) and ISI-mark photos (QCO) are evidence and must be seller-provided; never AI-generated.**

### 10.2 Image set

| Slot              | Source                                                         | Amazon                      | Flipkart                 | Meesho (max 4)                                                     |
| ----------------- | -------------------------------------------------------------- | --------------------------- | ------------------------ | ------------------------------------------------------------------ |
| Main/front        | SoT, background removed → white, padded to frame-fill target   | Required, strictest         | Required, white          | Image 1; shipping-optimised variant; packaging front if pre-packed |
| Alternate angles  | Seller photos preferred; AI "inferred view" only with approval | Allowed (no inferred views) | Allowed                  | Allowed                                                            |
| Lifestyle         | AI scene around locked product pixels                          | Secondary                   | Secondary                | Secondary                                                          |
| Infographic       | AI layout + text from verified facts                           | Secondary (text OK)         | Check vertical           | Avoid (no text)                                                    |
| Dimension/size    | From master dimensions                                         | Secondary                   | Secondary                | Secondary                                                          |
| Size chart        | From master size chart                                         | Secondary                   | Often required (apparel) | Secondary                                                          |
| What's in the box | Composite of SoT photos                                        | Secondary                   | Secondary                | Optional                                                           |
| Packaging back    | Seller photo                                                   | —                           | —                        | Image 2 if pre-packed                                              |
| Model wear        | Real preferred; AI opt-in with warning                         | Risky                       | Check                    | Check                                                              |

### 10.3 Pipeline

Segmentation → **mask lock** (product pixels frozen) → generation outside mask → compositing (lighting/shadows without altering product) → fidelity QC → channel QC.

### 10.4 Fidelity QC

| Check                    | Method                                  | Fail action                  |
| ------------------------ | --------------------------------------- | ---------------------------- |
| Product pixels unchanged | Pixel diff inside mask                  | Hard fail                    |
| Colour accuracy          | ΔE on product region                    | Fail above threshold         |
| Item count / accessories | Object detection vs master              | Hard fail                    |
| Scale plausibility       | Reference objects vs master dimensions  | Review                       |
| Brand/print preservation | Region similarity                       | Fail if degraded             |
| Unwanted text/logos      | OCR + logo detection                    | Fail on main; warn elsewhere |
| Distortion               | Aspect ratio vs SoT (no stretch/shrink) | Hard fail                    |

### 10.5 Channel QC

- Amazon: RGB 255 white, ≥ 85% fill, ≥ 1000 px, no text/props.
- Flipkart: white primary, no stickers/text/watermarks.
- Meesho: JPEG, RGB, no text/watermark on Image 1, no price/logo overlays, no distortion, not partial, not blurry, no duplicates, max 4.

### 10.6 One-photo sellers

From one SoT: cleaned main, lifestyle composites, dimension image, size chart, infographics. Not: honest back/side views. Guided mobile capture nudges a 4-photo minimum (front, back, side, detail).

---

## 11. Meesho Shipping Optimiser

### 11.1 Evidence

- Many third-party tools claim Meesho estimates shipping slab partly from the listing image; others say images are at most one signal. **Meesho does not document this.**
- Solid facts: shipping is system-calculated and not editable; zero commission makes shipping and returns the main costs; the template has **no packed weight/dimension field** (consistent with Meesho estimating packaging by other means).
- Reverse shipping reportedly uses the same slab.

Treat as **experiment-driven optimisation**, not a formula.

### 11.2 Flow

1. **Fix the real package first:** compute dead vs volumetric weight from master packed dimensions; show distance to the next slab; packaging advisor (polybag/box sizes).
2. **Generate compliant presentation variants (8–12):** vary only frame fill (uniform scaling), angle, presentation state for soft goods (folded/rolled/stacked if shipped that way), background, canvas. All pass fidelity QC.
3. **Seller tests in panel (manual):** records the shipping charge Meesho shows (form or screenshot OCR). No panel automation.
4. **Learn:** opt-in anonymised aggregation across sellers ranks presentations per category.
5. **Monitor drift:** alert when previously good presentations start costing more.

### 11.3 Integrity guardrails

| Allowed                                               | Not allowed                                          |
| ----------------------------------------------------- | ---------------------------------------------------- |
| Tighter crop / higher frame fill (uniform scale)      | Stretching, shrinking, or distorting the product     |
| Folded/rolled presentation for items shipped that way | Folded presentation for items that can't ship folded |
| Angle and background changes                          | Hiding included items; altering shape/colour/print   |
| Real packaging optimisation                           | Declaring weight/dimensions below reality            |

Savings are shown as the seller's own measured before/after, never guaranteed.

---

## 12. Human-in-the-loop (manual) fields

### 12.1 Amazon

| Item                                            | Blocks publish?        |
| ----------------------------------------------- | ---------------------- |
| GTIN source / exemption / Brand Registry status | Yes                    |
| Restricted category approvals                   | Yes                    |
| Dangerous goods classification                  | Yes (where applicable) |
| Final browse node (low confidence)              | Yes                    |
| Fulfillment choice (FBA/Easy Ship/Self Ship)    | Yes                    |
| Selling price                                   | Yes                    |
| A+ Content approval                             | No                     |

### 12.2 Flipkart

| Item                                      | Blocks publish?    |
| ----------------------------------------- | ------------------ |
| Brand approval and documents              | Yes                |
| FSN latching confirmation                 | Yes                |
| Excel upload in Seller Hub (new products) | Yes (publish step) |
| Tax code selection                        | Yes                |
| Procurement type and dispatch SLA         | Yes                |
| Variant family sign-off                   | Yes                |
| QC appeals                                | No                 |

### 12.3 Meesho

| Item                                                                      | Blocks publish?           |
| ------------------------------------------------------------------------- | ------------------------- |
| Template selection confirmation (ambiguous categories)                    | Yes                       |
| Upload image ZIP via Images Bulk Upload; paste links                      | Yes                       |
| Upload filled sheet in Supplier Panel (correct category)                  | Yes (publish step)        |
| Catalog grouping (Group ID) decisions                                     | Yes                       |
| Meesho Price and Wrong/Defective discount                                 | Yes                       |
| Packaging photos (pre-packed), ISI photo (QCO), licence docs (characters) | Yes when flag applies     |
| Shipping test recording                                                   | No                        |
| Download processed file and upload back to ListingPilot                      | No (strongly recommended) |

### 12.4 Cross-platform

All ComplianceBlock fields; certifications with expiry tracking; Product Flags.

---

## 13. Channel adapters and publishing

### 13.1 Amazon adapter

- SP-API OAuth (public app).
- Search catalog by GTIN, then brand + model → propose offer-only on confident match (human confirms) else new product.
- Fetch/cache product type schema → build payload → local JSON Schema validation → validation preview → `putListingsItem` (small batches) or `JSON_LISTINGS_FEED` (bulk).
- Parent-first variation submission; rate-limited queue.
- Subscribe to listing and schema change notifications; map issues to master fields.
- Title drift detection (live title vs published title, to catch Amazon AI rewrites).

### 13.2 Flipkart adapter

- **API mode (existing FSN):** v3 payload (price, tax, fulfillment, packages, locations, address labels); diff against last payload; confirm overwrites.
- **Template mode (new products):** bundled or seller-supplied vertical templates (same library pattern as Meesho, §13.3); generate pre-validated sheets; seller uploads in Seller Hub; import upload status report and map errors.

### 13.3 Meesho adapter: bundled template library

#### 13.3.1 Decision

Official Meesho templates are bundled in the codebase. The backend selects, fills (AI + deterministic code), validates and delivers finished files. The seller uploads them manually.

#### 13.3.2 Repository layout

```
/templates/meesho/
  registry.json
  raw/                       # official .xlsx files (source of truth)
    10000_tshirts_v51_2Prices_GSTIN.xlsx
    10001_shirts_v56_2Prices_GSTIN.xlsx
    10058_bedsheets-kids_v52_2Prices_GSTIN.xlsx
    13178_sneakers-men_v33_2Prices_GSTIN.xlsx
  compiled/                  # generated JSON, never hand-edited
  mappings/
    shared_core.yaml         # ~33 fields common to all templates
    category/<id>.yaml       # category-specific mappings
  rules/
    meesho_global.yaml       # MV-01..MV-20
    category/<id>.yaml
  fixtures/                  # golden-file tests
```

#### 13.3.3 Registry entry

```json
{
	"category_id": 10000,
	"version": 51,
	"type": "BASE",
	"experiment_flag": "pre_tp_experiment",
	"variant": ["2Prices", "GSTIN"],
	"category_path": "Men Fashion/Mens Clothing/Men Top Wear/Tshirts",
	"sheet_name": "Tshirts-Fill this",
	"data_start_row": 5,
	"raw_file": "raw/10000_tshirts_v51_2Prices_GSTIN.xlsx",
	"compiled_file": "compiled/10000_v51.json",
	"sha256": "…",
	"downloaded_on": "2026-10-28",
	"verified_on": "2026-10-28",
	"status": "active",
	"supersedes": null
}
```

#### 13.3.4 Template anatomy

| Sheet                  | Contents                                                                                                                  | Use                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| Instructions           | Rules, image standards, declaration, hidden fingerprint                                                                   | Fingerprint; AI-drafted, admin-verified rules |
| `<Category>-Fill this` | Row 1 category path · Row 2 Compulsory/Optional · Row 3 field name + description · Row 4 tutorial links · data from row 5 | Output target                                 |
| Example Sheet          | Sample rows (may contain errors)                                                                                          | Ignored for rules                             |
| Validation Sheet       | Allowed values per column                                                                                                 | Exact dropdown dictionary                     |
| Return Reasons         | Returns allowed under each price                                                                                          | Returns advisor                               |

#### 13.3.5 Build-time compiler

- Extracts fingerprint, variant, category path, fields, required markers, units, exact allowed values, return-reason matrix, data start row.
- **Fails the build** if any template field lacks a mapping.
- Produces a version diff report on every change.
- Golden-file regression tests per template.

#### 13.3.6 Field model (summary; full list in Appendix A)

- **Shared core:** Product Name, Variation, Meesho Price, W/D Discount, MRP, GST %, HSN, Net Weight, Inventory, Country of Origin, Manufacturer/Packer/Importer (9 fields), Generic Name, Net Quantity, Images 1–4, Style ID, SKU ID, Brand Name, Group ID, Product Description, Brand.
- **Always filled by ListingPilot (even if optional):**

| Field    | Rule                                      | Generation                                                           |
| -------- | ----------------------------------------- | -------------------------------------------------------------------- |
| Style ID | Same across sizes, differs across colours | `{family_code}-{colour_code}`                                        |
| SKU ID   | Unique per variation                      | `{family_code}-{colour_code}-{size_code}`, unique across all exports |
| Group ID | Groups products into one catalog          | Family-level or merchandiser-defined                                 |

- **Brand:** exact match in dropdown → fill both; else Brand Name only + warning. Never choose a "closest" brand.
- **Character:** default "Not Applicable"; any other value requires licence document; AI never auto-selects.
- **Size measurements:** per size row from SizeChart; snapped to allowed steps; flag large snaps.

#### 13.3.7 Template freshness

- ListingPilot ops maintains its own Meesho supplier account(s) (GST; non-GST if supported) and re-downloads supported templates weekly at launch via PR.
- Error-spike detection across sellers flags likely-stale templates.
- **Seller override:** seller uploads their panel's blank template; compiled on the fly, diffed, used for fill, queued for ops review.
- Freshness status per template; warning when `verified_on` exceeds threshold (e.g., 30 days).

#### 13.3.8 Template selection

1. Narrow by master category + flags (gender, age group, pre-packed) against registry category paths.
2. AI ranks candidates using category paths and field descriptions.
3. Seller confirms when ambiguous or first time in that category; choice stored on the family.
4. No fit → "Meesho template not yet supported" + override option; request logged.

Launch coverage: the 4 provided categories + next 20–30 by seller demand.

#### 13.3.9 Fill pipeline

1. Group products by template and Group ID (one sheet per category).
2. Resolve values: deterministic fields from master; dropdowns via stored mapping rules then AI suggestions; text fields AI-generated under Meesho rules.
3. Validate (MV-01–MV-20); blocked rows go to review queue, excluded from file.
4. Insert panel-generated image links.
5. Copy raw template; write data rows only; IDs/pincodes/EAN as text; numbers as numbers.
6. Package for delivery.

AI never writes directly into the sheet.

#### 13.3.10 Image-link dependency (two-step wizard)

1. ListingPilot provides image ZIP (JPEG/RGB, `SKU_slot.jpg`).
2. Seller uploads via Images Bulk Upload in the panel and copies links.
3. Seller pastes links; ListingPilot matches by filename; coverage check for Image 1.
4. ListingPilot generates the final sheet.

No "sheet without images" download (guaranteed rejection).

#### 13.3.11 Delivery

ZIP per batch with one `.xlsx` per category (e.g., `ListingPilot_Tshirts_10000_v51_2026-10-28.xlsx`) and an upload checklist: Meesho category path to select, product and catalog counts, held-back rows with reasons, reminder to return the processed file.

#### 13.3.12 Feedback loop

Seller uploads Meesho's processed file (ERROR STATUS/MESSAGE) → rows matched by SKU ID and template version → errors mapped to master fields with fix suggestions → correction sheet for failed rows only. Builds the MeeshoErrorDictionary and feeds staleness detection.

#### 13.3.13 Meesho content rules

- **Product Name:** brand (if any) + generic product + key attribute (colour/fabric/style); no weight, dimension, price, promo words, portal names.
- **Description:** 2–4 sentences: material, fit/use, care, what's included; fact-grounded.
- **Generic Name:** from template's allowed list.

### 13.4 Adapter interface (future channels)

`getCategorySchema() · classify() · mapAttributes() · buildPayload() · validate() · publish() (API or file) · ingestStatus() · importExisting()`

---

## 14. Meesho two-price model and returns advisor

- **Meesho Price:** all return reasons (fit, changed mind, lower price elsewhere, late delivery, defects, etc.).
- **Wrong/Defective price** (= Meesho Price − discount): only wrong/defective reasons (different product, broken/torn, wrong size/colour delivered, missing parts, short quantity, dirty/stained, poor quality).
- Constraints: Meesho Price < MRP; W/D price < Meesho Price.
- **Template inconsistency:** instructions mention a W/D _price_; the column is a _discount (₹)_. Store the discount; compute and display the price. Confirm in Phase 0.
- **Advisor:** shows discount and resulting price, estimated preference-returns avoided (seller history or editable category defaults), net effect per order. Seller decides; default per workspace (template's ₹22 recommendation or blank).

---

## 15. Validation rules

### 15.1 General (all channels)

- Schema/template required fields present; enum/dropdown exact matches.
- Length/byte limits from live schema or compiled template.
- Banned/restricted terms; no unsupported claims.
- ComplianceBlock complete and human-verified.
- Variant completeness and uniqueness.
- Image QC per channel.
- Flags satisfied (documents present where required).

### 15.2 Meesho rules

| ID    | Rule                                                                                              | Severity     |
| ----- | ------------------------------------------------------------------------------------------------- | ------------ |
| MV-01 | All Compulsory columns non-empty                                                                  | Block        |
| MV-02 | Dropdown values exactly match Validation Sheet (case/spelling preserved)                          | Block        |
| MV-03 | Meesho Price < MRP; MRP > 0                                                                       | Block        |
| MV-04 | Discount (if set) > 0 and resulting price > 0                                                     | Block        |
| MV-05 | HSN in template list; GST % consistent with HSN (and price where applicable)                      | Block        |
| MV-06 | Pincodes 6 digits; addresses include town/district and state                                      | Block        |
| MV-07 | Country of Origin ≠ India ⇒ genuine importer details                                              | Block        |
| MV-08 | SKU ID unique in sheet and across prior exports                                                   | Block        |
| MV-09 | Style ID same across sizes, different across colours                                              | Block        |
| MV-10 | One category per Group ID; ≥ 3 products recommended                                               | Block / Warn |
| MV-11 | Image 1 present; JPEG, RGB, panel-generated link format                                           | Block        |
| MV-12 | Image QC (no text/watermark on Image 1, no overlays, no distortion, not partial/blurry/duplicate) | Block / Warn |
| MV-13 | Product Name free of weight/dimension/price/portal names/restricted keywords                      | Block        |
| MV-14 | Pre-packed ⇒ Images 1–2 are seller packaging photos                                               | Block        |
| MV-15 | QCO ⇒ CM/L, IS Number, ISI mark photo                                                             | Block        |
| MV-16 | Character ≠ "Not Applicable" ⇒ licence on file                                                    | Block        |
| MV-17 | EAN/UPC 13 digits (UPC prefixed with 0)                                                           | Block        |
| MV-18 | Size measurements for every size row, within dropdown range                                       | Block        |
| MV-19 | Product Description present                                                                       | Warn         |
| MV-20 | Template stale/superseded                                                                         | Warn         |

---

## 16. Functional requirements

Priority: **P0** = MVP · **P1** = v1.0 · **P2** = later.

### 16.1 Master Catalogue

| ID       | Requirement                                                          | P   |
| -------- | -------------------------------------------------------------------- | --- |
| FR-MC-01 | Families and variants with configurable variation theme              | P0  |
| FR-MC-02 | Canonical master attribute dictionary (types, units, allowed values) | P0  |
| FR-MC-03 | Provenance, confidence, verifier, timestamp on every value           | P0  |
| FR-MC-04 | Mandatory ComplianceBlock before any export                          | P0  |
| FR-MC-05 | Bulk edit with preview and undo                                      | P0  |
| FR-MC-06 | Field-level history and rollback                                     | P1  |
| FR-MC-07 | Stale-marking of dependent content on fact change                    | P0  |
| FR-MC-08 | Brand records with per-channel status and document expiry alerts     | P1  |

### 16.2 Ingestion

| ID       | Requirement                                                          | P   |
| -------- | -------------------------------------------------------------------- | --- |
| FR-IN-01 | CSV/XLSX import with mapping UI and presets                          | P0  |
| FR-IN-02 | Import existing Amazon listings via API (de-dup by SKU/GTIN)         | P1  |
| FR-IN-03 | Import Flipkart/Meesho export files                                  | P1  |
| FR-IN-04 | AI extraction from photos, packaging, PDFs with per-field confidence | P0  |
| FR-IN-05 | Cross-channel conflict flagging                                      | P1  |

### 16.3 Taxonomy & Mapping

| ID       | Requirement                                                                     | P   |
| -------- | ------------------------------------------------------------------------------- | --- |
| FR-TX-01 | Suggest Amazon product type, Flipkart vertical, Meesho template with confidence | P0  |
| FR-TX-02 | Human confirmation below threshold                                              | P0  |
| FR-TX-03 | Enum/dropdown mapping with reusable rules                                       | P0  |
| FR-TX-04 | Auto-refresh Amazon schemas on notifications                                    | P1  |
| FR-TX-05 | Compile Flipkart/Meesho templates into rule sets                                | P0  |
| FR-TX-06 | Template version diffing with impacted SKUs                                     | P1  |

### 16.4 Flags & Conditional Rules

| ID        | Requirement                                                        | P   |
| --------- | ------------------------------------------------------------------ | --- |
| FR-CND-01 | Product Flag library mapped to channel fields; human confirmation  | P0  |
| FR-CND-02 | Compile Amazon conditional schemas into rules                      | P0  |
| FR-CND-03 | Extract template rules; AI-drafted, admin-verified conditions      | P0  |
| FR-CND-04 | Dynamic progressive-disclosure forms                               | P0  |
| FR-CND-05 | Block structurally invalid exports (e.g., customisable → Flipkart) | P0  |
| FR-CND-06 | Impact analysis and one-way-door warnings                          | P1  |
| FR-CND-07 | Per-channel completeness meter                                     | P0  |

### 16.5 AI Content

| ID       | Requirement                                      | P   |
| -------- | ------------------------------------------------ | --- |
| FR-AI-01 | Per-channel titles within schema/template limits | P0  |
| FR-AI-02 | Amazon Item Highlights ≤ 125 chars               | P0  |
| FR-AI-03 | Bullets, descriptions, keywords per channel      | P0  |
| FR-AI-04 | Fact-ID grounding; strip unreferenced claims     | P0  |
| FR-AI-05 | Banned-term lists (global, channel, brand)       | P0  |
| FR-AI-06 | Byte-counted Amazon backend keywords; exclusions | P0  |
| FR-AI-07 | Brand voice profiles                             | P1  |
| FR-AI-08 | N alternatives per field                         | P1  |
| FR-AI-09 | Bulk generation with per-SKU failure reporting   | P0  |
| FR-AI-10 | Keyword inputs and suggestions                   | P1  |
| FR-AI-11 | Hindi/regional generation                        | P2  |
| FR-AI-12 | A+ Content drafts                                | P2  |

### 16.6 Media & Images

| ID        | Requirement                                                          | P   |
| --------- | -------------------------------------------------------------------- | --- |
| FR-MD-01  | Background detection; flag non-pure-white for Amazon                 | P0  |
| FR-MD-02  | Auto-whiten and pad/crop to frame-fill target; keep originals        | P0  |
| FR-MD-03  | Detect text, logos, watermarks, price stickers                       | P0  |
| FR-MD-04  | Per-channel minimum resolution                                       | P0  |
| FR-MD-05  | Channel derivatives and SKU/slot-named ZIP exports                   | P0  |
| FR-MD-06  | Paste-back of Meesho image links matched by filename                 | P0  |
| FR-IMG-01 | SoT required per variant; per-colour SoT unless AI recolour approved | P0  |
| FR-IMG-02 | Mask-locked generation                                               | P0  |
| FR-IMG-03 | Fidelity QC on every generated image                                 | P0  |
| FR-IMG-04 | Slot restrictions by image origin per channel                        | P0  |
| FR-IMG-05 | Lifestyle, infographic, dimension, size chart, in-the-box images     | P1  |
| FR-IMG-06 | Inferred views labelled; excluded from Amazon                        | P0  |
| FR-IMG-07 | Guided mobile capture                                                | P1  |
| FR-IMG-08 | AI model-wear (opt-in, warning)                                      | P2  |
| FR-MT-13  | Packaging and ISI photo slots never AI-generated                     | P0  |

### 16.7 Meesho Shipping Optimiser

| ID        | Requirement                                                 | P   |
| --------- | ----------------------------------------------------------- | --- |
| FR-SHP-01 | Dead vs volumetric weight; distance to next slab            | P0  |
| FR-SHP-02 | Packaging advisor                                           | P1  |
| FR-SHP-03 | 8–12 compliant presentation variants (uniform scaling only) | P0  |
| FR-SHP-04 | Record observed charges (form/OCR)                          | P0  |
| FR-SHP-05 | Opt-in anonymised cross-seller ranking                      | P1  |
| FR-SHP-06 | Drift detection                                             | P2  |
| FR-SHP-07 | Lock declared weight/dims to master                         | P0  |
| FR-SHP-08 | No automated Supplier Panel interaction                     | P0  |

### 16.8 Meesho Template Library & Export

| ID       | Requirement                                                     | P   |
| -------- | --------------------------------------------------------------- | --- |
| FR-TL-01 | Bundle raw templates with registry                              | P0  |
| FR-TL-02 | Build-time compiler; build fails on unmapped fields             | P0  |
| FR-TL-03 | Version diff report per change                                  | P0  |
| FR-TL-04 | Golden-file regression tests                                    | P0  |
| FR-TL-05 | Template selection (path + flags + AI) with confirmation        | P0  |
| FR-TL-06 | Two-step export wizard (image links before sheet)               | P0  |
| FR-TL-07 | Export ZIP per category + upload checklist                      | P0  |
| FR-TL-08 | Freshness status and staleness warnings                         | P0  |
| FR-TL-09 | Cross-seller error-spike detection → ops alert                  | P1  |
| FR-TL-10 | Seller-override template upload, on-the-fly compile, ops review | P1  |
| FR-TL-11 | Log unsupported-category requests                               | P1  |
| FR-MT-01 | Runtime parsing of seller-uploaded templates (override path)    | P1  |
| FR-MT-02 | Write into original file, data rows only                        | P0  |
| FR-MT-03 | Preserve dropdown strings exactly                               | P0  |
| FR-MT-04 | Deterministic Style/SKU/Group IDs; global uniqueness            | P0  |
| FR-MT-05 | Run MV-01–MV-20 pre-export                                      | P0  |
| FR-MT-06 | JPEG/sRGB images, max 4 per SKU                                 | P0  |
| FR-MT-07 | Import processed files; map errors; correction sheets           | P0  |
| FR-MT-08 | Learned Meesho error dictionary                                 | P1  |
| FR-MT-10 | Size chart entry/extraction with dropdown snapping              | P0  |
| FR-MT-11 | Returns advisor (W/D discount)                                  | P1  |
| FR-MT-12 | Brand dropdown exact match with Brand Name fallback             | P0  |

### 16.9 Validation & Review

| ID       | Requirement                                              | P   |
| -------- | -------------------------------------------------------- | --- |
| FR-VR-01 | Per-channel readiness score (blocking vs warning)        | P0  |
| FR-VR-02 | Variant completeness before first Flipkart export        | P0  |
| FR-VR-03 | Duplicate detection (catalogue and prior Meesho exports) | P0  |
| FR-VR-04 | Typed manual tasks with owner, due date, blocking flag   | P0  |
| FR-VR-05 | Maker-checker approvals                                  | P1  |
| FR-VR-06 | Master vs channel diff view                              | P1  |

### 16.10 Publishing & Feedback

| ID       | Requirement                                                     | P   |
| -------- | --------------------------------------------------------------- | --- |
| FR-PB-01 | Amazon catalog search before create; offer-only and new flows   | P0  |
| FR-PB-02 | Amazon validation preview                                       | P0  |
| FR-PB-03 | Amazon rate-limited queue and feeds                             | P0  |
| FR-PB-04 | Flipkart API publish (existing FSN) with overwrite confirmation | P1  |
| FR-PB-05 | Flipkart template generation (new products)                     | P0  |
| FR-PB-06 | Import Flipkart/Meesho result files; map errors                 | P0  |
| FR-PB-07 | Plain-language error explanations and fixes                     | P1  |
| FR-PB-08 | Master change propagation (API push / re-export)                | P1  |
| FR-PB-09 | Per-channel price calculator                                    | P1  |
| FR-PB-10 | Amazon live-title drift detection                               | P1  |

### 16.11 Platform & Admin

| ID       | Requirement                                               | P   |
| -------- | --------------------------------------------------------- | --- |
| FR-AD-01 | Multi-tenant workspaces with RBAC                         | P0  |
| FR-AD-02 | Agency mode                                               | P1  |
| FR-AD-03 | Audit log (publishes, approvals, AI generations, exports) | P0  |
| FR-AD-04 | Admin-editable channel rule sets                          | P0  |
| FR-AD-05 | Usage metering                                            | P1  |

---

## 17. Non-functional requirements

| Area              | Requirement                                                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Performance       | Single-SKU content for 3 channels < 30 s (p95); 1,000 SKUs < 1 h; 5,000-row template export < 2 min; image variant generation < 60 s per SKU (p95) |
| Scalability       | 100k variants and 1M media assets per workspace; horizontally scalable workers                                                                     |
| Reliability       | Idempotent, resumable jobs; no double submission; 99.5% uptime                                                                                     |
| Security          | Marketplace credentials encrypted (KMS), never exposed to frontend; TLS; SSO (P2)                                                                  |
| Privacy           | DPDP Act 2023 compliance; no training on seller data without opt-in; India data residency preferred; shipping-test sharing opt-in and anonymised   |
| AI accountability | Every generation logged (model, prompt version, inputs, grounding facts) and reproducible                                                          |
| File fidelity     | Exported templates byte-compatible with originals except data cells                                                                                |
| Usability         | First product to 3 channels within 30 min of signup; mobile-responsive review queue and photo capture                                              |
| Maintainability   | Rules as data; stable adapter interface; template refresh via PR                                                                                   |
| Observability     | Per-channel dashboards (volume, acceptance, top errors); rejection-spike alerts; template freshness dashboard                                      |

---

## 18. Architecture and tech stack

### 18.1 Logical flow

Ingestion → **Master Catalogue** → Taxonomy & Mapping + Flags/Rules → AI Content Studio + Media Studio → Validation Engine → Review Queue → Publishing Orchestrator → Amazon Adapter (API) / Flipkart Adapter (API or file) / Meesho Adapter (bundled template file) → Feedback Ingestor (Amazon notifications, imported result files) → back to master and validation.

### 18.2 Stack

| Layer             | Choice                                                                                | Rationale                                          |
| ----------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Frontend          | Next.js + TypeScript; data grid (e.g., AG Grid)                                       | Spreadsheet-like catalogue work                    |
| API               | Python (FastAPI) recommended (or NestJS)                                              | Strong Excel and image tooling                     |
| Database          | PostgreSQL + JSONB; pgvector                                                          | Relational master + flexible payloads + embeddings |
| Workflows         | Temporal (or BullMQ/Redis initially)                                                  | Long-running, retryable, rate-limited jobs         |
| Storage           | S3-compatible (Mumbai region)                                                         | Images, templates, exports                         |
| Image processing  | Segmentation model + inpainting/compositing; libvips/Pillow                           | Mask-locked generation; JPEG/RGB conversion        |
| LLM               | Claude via API (Sonnet-class for bulk, Opus-class for hard classification/extraction) | Grounded, constrained generation; vision           |
| Schema validation | Ajv / jsonschema                                                                      | Amazon payload validation                          |
| Excel             | openpyxl (preserve validations/formatting)                                            | Write into original templates                      |
| Template compiler | CI job (Python)                                                                       | Compile, diff, test bundled templates              |
| Auth              | Clerk/Auth0 or Keycloak                                                               | Multi-tenant RBAC                                  |

### 18.3 Key technical decisions

- Schema- and template-driven limits; nothing hard-coded.
- Bundled raw templates are the source of truth; compiled JSON for logic; outputs written into copies of raw files.
- Deterministic validation wraps every AI output.
- No scraping; no seller-panel automation.

---

## 19. Risks

| Risk                                          | Impact                       | Mitigation                                                                     |
| --------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------ |
| ToS violation via panel automation            | Seller suspension            | No RPA; official APIs and manual uploads only                                  |
| Platform rule changes                         | Mass rejections              | Schema-driven limits; rule sets; rejection-spike alerts                        |
| AI hallucinated claims                        | Policy/consumer-law exposure | Fact grounding, claim stripping, approvals                                     |
| AI image misrepresentation                    | Returns, suppression         | SoT anchoring, mask lock, fidelity QC, slot limits                             |
| Amazon AI image policy tightening             | Suppression                  | Image origin tracking enables bulk replacement                                 |
| Flipkart API access not granted               | Template-only Flipkart       | Template mode is first-class                                                   |
| **Bundled Meesho templates go stale**         | Upload failures              | Weekly ops refresh; error-spike detection; seller override; freshness warnings |
| Account-specific Meesho templates (A/B tests) | Mismatch for some sellers    | Phase 0 verification; override path                                            |
| Meesho changes image-based shipping logic     | Optimiser value drops        | Packaging optimisation still valid; drift detection; no guarantees             |
| Shipping-optimised images seen as misleading  | Returns, account action      | Integrity guardrails; locked weights                                           |
| Dropdown strings "corrected"                  | Rejections                   | Exact-string preservation tests                                                |
| Legal Metrology non-compliance                | Fines                        | Mandatory ComplianceBlock gate; human-only                                     |
| Wrong category selected in Meesho panel       | Rejection                    | Category path printed per file in checklist                                    |
| Template redistribution terms                 | Partner/legal issue          | Review Meesho supplier terms / partner team before launch                      |
| SP-API rate limits                            | Slow publishing              | Feeds, queueing                                                                |

---

## 20. Roadmap

### Phase 0 — Discovery (3–4 weeks)

- Seller interviews (15–20) across personas.
- Set up ListingPilot Meesho supplier account(s); download templates for top 25–30 categories.
- Collect Flipkart vertical templates for target categories.
- Register as SP-API developer; apply for Flipkart API access.
- Resolve open questions (§21).
- Benchmark image segmentation/inpainting providers on target categories.

### Phase 1 — MVP (10–12 weeks)

- Master Catalogue, flags, dynamic forms, CSV import, AI extraction.
- Classification and mapping; AI content for all 3 channels.
- Media Studio basics: SoT, cleanup, mask-locked composites, channel QC.
- Validation and review queue.
- Amazon API publishing.
- Meesho bundled template library (compiler, registry, golden tests), export wizard, error import.
- Flipkart template export.
- Shipping slab calculator; presentation variants; manual test recording.
- Focus categories: apparel (T-shirts, shirts), footwear (sneakers), home (bedsheets).

### Phase 2 — v1.0 (8–10 weeks)

- Amazon listing import; Flipkart API mode; sync propagation.
- Brand voice; returns advisor; price calculator; approvals; agency mode.
- Infographics, size charts, packaging advisor; cross-seller shipping learning.
- Error dictionaries; staleness detection; seller-override templates.

### Phase 3 — v2

- Hindi/regional content; A+ Content; AI model-wear (if policy permits); drift detection.
- Additional channels (Myntra, Ajio, JioMart, ONDC); OMS integrations; listing performance analytics.

---

## 21. Open questions and Phase 0 checklist

### Product

1. Primary customer: own brands or SaaS for third-party sellers?
2. Launch categories beyond the four templates provided?
3. Auto-publish tolerance for high-confidence AI content?
4. Cross-seller shipping-data sharing (opt-in) — yes/no?
5. Image generation stack: in-house vs API provider?

### Meesho (requires real accounts)

6. Importer fields (marked Compulsory) for Made-in-India products: what do accepted listings contain?
7. W/D column: discount vs price behaviour and display.
8. Image 1 for pre-packed goods: packaging front or product?
9. Non-GST (Enrolment ID) template variant: exists and differs how?
10. Where QC rejection reasons appear (processed file, panel, both)?
11. When the panel shows shipping charge for a new catalog?
12. Are templates identical across seller accounts (version, brand dropdown, experiment flag)?
13. Can generated image links be reused across multiple sheets/correction uploads?
14. Meesho terms on redistributing templates within a commercial tool.

### Flipkart / Amazon

15. Flipkart API access timeline and scope.
16. Expected catalogue size per seller (drives feeds/Temporal at MVP).

---

## 22. References

**Amazon**

- Listings Items API — https://developer-docs.amazon.com/sp-api/docs/listings-items-api
- Manage product listings guide — https://developer-docs.amazon.com/sp-api/docs/manage-product-listings-guide
- Building listings management workflows — https://developer-docs.amazon.com/sp-api/docs/building-listings-management-workflows-guide
- Product Type Definitions API — https://developer-docs.amazon.com/sp-api/docs/product-type-definitions-api
- putListingsItem reference — https://developer-docs.amazon.com/sp-api/reference/putlistingsitem
- Listings Items API rate limits — https://developer-docs.amazon.com/sp-api/docs/listings-items-api-rate-limits
- Parent-child relationships — https://sellercentral.amazon.com/gp/help/external/8841
- Dangerous goods information — https://sellercentral.amazon.com/help/hub/reference/external/G34151
- Product ID guide (India) — https://sell.amazon.in/seller-blog/how-to-get-a-product-id-for-selling-on-amazon
- 75-character title change coverage — https://ppc.land/amazon-cuts-product-title-limit-to-75-characters-on-july-27/ ; https://sellerengine.com/amazon-product-title-update-2026/amp/

**Flipkart**

- Listing Management API overview — https://seller.flipkart.com/api-docs/listing-api-docs/LMAPIOverview.html
- Listing Management API reference — https://seller.flipkart.com/api-docs/listing-api-docs/LMAPIRef.html
- Create listings v3 — https://seller.flipkart.com/api-docs/listing-api-docs/v3/CreateListingsAPI.html
- Integrator FAQs (Fynd) — https://documentation.fynd.com/commerce/docs/openapi/listings-management/flipkart/faq-flipkart

**Meesho**

- Bulk catalog upload (learning hub) — https://supplier.meesho.com/learning-hub/lessons/how-to-list-your-catalogs-using-bulk-uploads
- How it works — https://supplier.meesho.com/how-it-works
- Official category templates (provided): Tshirts 10000 v51, Shirts 10001 v56, Bedsheets 10058 v52, Sneakers 13178 v33
- Shipping charges overview — https://www.shiprocket.in/blog/meesho-shipping-charges/
- Image-based shipping claims (third-party, unverified) — https://www.meeship.in/blog/reduce-meesho-shipping-cost ; cautious view — https://imageready.in/blog/how-to-reduce-meesho-shipping-charges/

**Compliance**

- Legal Metrology and e-commerce — https://ssrana.in/corporate-laws/legal-metrology-and-packaging/
- Country of origin on e-commerce — https://www.medianama.com/2020/07/223-country-of-origin-e-commerce/

_Note: third-party sources are marked where claims are unverified. Re-verify all platform rules during Phase 0._

---

## Appendix A: Meesho template field inventory

### A.1 Shared core (all four templates)

| #     | Field                                 | Status     | Notes                      |
| ----- | ------------------------------------- | ---------- | -------------------------- |
| 1     | ERROR STATUS                          | System     | Filled by Meesho           |
| 2     | ERROR MESSAGE                         | System     | Filled by Meesho           |
| 3     | Product Name                          | Compulsory | No weight/dimension/price  |
| 4     | Variation                             | Compulsory | Size dropdown per category |
| 5     | Meesho Price                          | Compulsory | < MRP                      |
| 6     | Wrong/Defective Return Discount (₹)   | Optional   | Recommended ₹22            |
| 7     | MRP                                   | Compulsory | INR                        |
| 8     | GST %                                 | Compulsory | Dropdown (e.g., 5, 18)     |
| 9     | HSN ID                                | Compulsory | Category-limited dropdown  |
| 10    | Net Weight (gms)                      | Compulsory | Excludes packaging         |
| 11    | Inventory                             | Compulsory |                            |
| 12    | Country of Origin                     | Compulsory | Dropdown                   |
| 13–15 | Manufacturer Name / Address / Pincode | Compulsory |                            |
| 16–18 | Packer Name / Address / Pincode       | Compulsory |                            |
| 19–21 | Importer Name / Address / Pincode     | Compulsory | Domestic behaviour TBC     |
| —     | Generic Name                          | Compulsory |                            |
| —     | Net Quantity (N)                      | Compulsory | Units in pack              |
| —     | Image 1 (Front)                       | Compulsory | Panel-generated link       |
| —     | Image 2–4                             | Optional   | Panel-generated links      |
| —     | Product ID / Style ID                 | Optional   | Always filled by ListingPilot |
| —     | SKU ID                                | Optional   | Always filled by ListingPilot |
| —     | Brand Name                            | Optional   | Free text                  |
| —     | Group ID                              | Optional   | Always filled by ListingPilot |
| —     | Product Description                   | Optional   | ListingPilot fills            |
| —     | Brand                                 | Optional   | Closed dropdown            |

### A.2 Category-specific

| Template                     | Compulsory                                                                                                                                  | Optional                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| T-shirts (10000)             | Color, Fabric, Fit/Shape, Neck, Occasion, Pattern, Print/Pattern Type, Sleeve Length, Chest/Length/Shoulder Size (inch)                     | EAN/UPC, Character, Hemline, Length, Number of Pockets      |
| Shirts (10001)               | Color, Fabric, Fit/Shape, Neck, Occasion, Pattern, Print/Pattern Type, Sleeve Length, Chest/Length/Shoulder Size (inch)                     | Closure, Hemline, Length, Number of Pockets, Sleeve Styling |
| Sneakers (13178)             | Ankle Height, Color, Fastening & Back Detail, Heel Type, Insole, Material, Pattern, Sole Material, Type, Waterproof, Foot Length/Width (cm) | CM/L Number, IS Number, Ornamentation                       |
| Bedsheets (10058, Kids path) | Color, Fabric, Included Components, Product Length/Width (cm), Thread Count, Bedsheet L/W Size (inch), Pillow L/W Size (inch)               | Ideal For, No. of Pillow Covers, Print/Pattern Type         |

### A.3 Return reasons matrix

| Reason                                  | Meesho Price | W/D Price |
| --------------------------------------- | ------------ | --------- |
| Did not like the fit                    | ✅           | ❌        |
| Size correct but too tight / too loose  | ✅           | ❌        |
| Did not like the product                | ✅           | ❌        |
| Changed my mind / Ordered by mistake    | ✅           | ❌        |
| Found lower price elsewhere             | ✅           | ❌        |
| Delivery was late                       | ✅           | ❌        |
| Completely different product            | ✅           | ✅        |
| Broken or torn (product or packaging)   | ✅           | ✅        |
| Wrong size / different colour delivered | ✅           | ✅        |
| Part missing / less quantity            | ✅           | ✅        |
| Dirty or stained                        | ✅           | ✅        |
| Poor quality or performance             | ✅           | ✅        |

---

## Appendix B: Glossary

| Term             | Meaning                                                        |
| ---------------- | -------------------------------------------------------------- |
| ASIN             | Amazon Standard Identification Number                          |
| FSN              | Flipkart Serial Number (catalog product ID)                    |
| LID              | Flipkart Listing ID (seller offer)                             |
| SP-API           | Amazon Selling Partner API                                     |
| PTD              | Amazon Product Type Definitions                                |
| SoT              | Source of Truth image (seller-provided photo)                  |
| QCO              | Quality Control Order (BIS)                                    |
| CM/L             | BIS licence number for a manufacturing unit                    |
| HSN              | Harmonised System of Nomenclature (tax classification)         |
| MRP              | Maximum Retail Price                                           |
| RTO              | Return to Origin                                               |
| W/D              | Wrong/Defective (Meesho return-restricted price)               |
| Group ID         | Meesho field grouping SKUs into one catalog                    |
| Style ID         | Meesho style code (same across sizes, differs across colours)  |
| Master Catalogue | ListingPilot's canonical product knowledge base                   |
| Product Flag     | Human-confirmed real-world toggle driving channel requirements |
| Golden file      | Expected output file used in regression tests                  |
