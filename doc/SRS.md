# ListingPilot — Software Requirements Specification

Version 2.1 · Thursday 29 October 2026

"Shall" means mandatory. Where this document and the PRD differ, this document wins.

## 1. Architecture

### 1.1 Components

| Component | Technology | Responsibility |
|---|---|---|
| Web app | Next.js with TypeScript | The only user interface. Talks only to the API |
| API | FastAPI | REST interface under the path prefix /api/v1; validation; orchestration; enforcement of approval and write rules |
| Worker | Celery | Background jobs: AI generation, publishing, polling, exports, imports, schema and template sync |
| Panel worker | Celery on a separate queue with a concurrency of one, using Playwright | Meesho panel automation only, one job at a time |
| Database | PostgreSQL 16 | All state. Neon in production, a local container for development and tests |
| Queue | Redis 7 | Job broker and results |
| Storage | A storage interface with two implementations: local disk and S3-compatible | Original images, renditions, generated files, cached schemas, template files |
| Mock marketplace server | FastAPI | Imitates Amazon SP-API, the Flipkart Seller API and captured Meesho panel pages; runs only in mock mode and tests |

### 1.2 Repository layout

| Folder | Contents |
|---|---|
| backend/app/core | Configuration, logging with redaction, database session, security, the write guard |
| backend/app/models | Database models |
| backend/app/schemas | Request and response models |
| backend/app/services | Business logic; every service receives the workspace and user context |
| backend/app/rules | Rule engine and the rule files in readable data format |
| backend/app/ai | AI providers, prompts, validation and retry loop |
| backend/app/media | Image checks, renditions and packaging |
| backend/app/adapters/amazon | SP-API client, schema ingestion, payload building, publishing, polling |
| backend/app/adapters/flipkart | Seller API client, listing sync, offer updates, template filling |
| backend/app/adapters/meesho/files | Template compiler, filling, rules, export packaging, processed-file import |
| backend/app/adapters/meesho/panel | Session manager, page selectors, panel operations |
| backend/app/jobs | Background job definitions |
| backend/app/api/v1 | REST routes |
| backend/migrations | Database migrations |
| backend/tests | Unit, integration, contract, golden-file and live test folders, plus fixtures |
| web/src | Pages, one folder per feature, shared components, API client |
| web/e2e | Browser journeys, split into mock and live |
| mockplace | The mock marketplace server and its scenario data |
| docs | All documents and bundled templates |
| data/pilot | Pilot data supplied by the owner; never committed |
| secrets | Saved sessions; never committed |
| artifacts | Test evidence and screenshots |

## 2. Configuration

All settings come from the .env file. The .env.example file documents every key with a one-line explanation and no real values.

| Setting | Purpose and rules |
|---|---|
| DATABASE_URL | Production database (Neon). Required. If unreachable, the API refuses to start and says why |
| TEST_DATABASE_URL | Test database. Must differ from DATABASE_URL, or the test run stops |
| REDIS_URL | Job broker. Required for the workers |
| CELERY_EAGER | Runs jobs inline; allowed only in tests |
| APP_PASSWORD | The shared password that protects the whole application until the SaaS phase |
| SECRET_KEY | Signs session cookies |
| MARKETPLACE_MODE | Either mock or live; defaults to mock. Per-marketplace overrides: AMAZON_MODE, FLIPKART_MODE and MEESHO_MODE |
| LIVE_WRITES_ENABLED | Defaults to false |
| LIVE_WRITE_SKUS | Comma-separated SKUs allowed to be written, or a single asterisk meaning all |
| AMAZON_SELLER_ID, AMAZON_LWA_CLIENT_ID, AMAZON_LWA_CLIENT_SECRET, AMAZON_REFRESH_TOKEN | Amazon private application credentials |
| AMAZON_MARKETPLACE_ID | Amazon.in marketplace identifier, A21TJRUUN4KGV |
| AMAZON_SPAPI_BASE and AMAZON_LWA_URL | The European SP-API endpoint (which serves India) and the Login with Amazon token address; pointed at the mock server in mock mode |
| FLIPKART_APP_ID, FLIPKART_APP_SECRET, FLIPKART_API_BASE | Flipkart self-access application credentials and API address |
| MEESHO_LOGIN_ID and MEESHO_PASSWORD | Meesho supplier login, used only as a fallback when no valid saved session exists |
| MEESHO_AUTOMATION | Defaults to false. When true, the panel worker runs |
| MEESHO_SESSION_FILE | Location of the saved Meesho session; defaults to a file in the secrets folder |
| ANTHROPIC_API_KEY, ANTHROPIC_MODEL, AI_PROVIDER | AI settings. The provider is either Anthropic or a fake provider used only in tests |
| STORAGE_BACKEND, STORAGE_DIR and the S3 endpoint, bucket and key settings | File storage |
| PUBLIC_MEDIA_BASE_URL | The public web address prefix for image renditions. Amazon downloads listing images from public addresses, so this is required for Amazon live publishing |
| DEMO_SEED | Loads synthetic demo data; never on in production |

### 2.1 Credential access rule

- All credentials are read through a single credential-access function that takes the workspace context and the marketplace.
- In the MVP that function reads .env. In the SaaS phase it is replaced by a per-workspace encrypted vault, and nothing else changes.
- The interface only ever shows whether a credential is present and whether its live check passed, never the value.

## 3. Tenancy and audit

- Every table owned by a workspace carries a workspace ID.
- Migrations create one default workspace and one default user.
- Every "who" field (created by, verified by, approved by, confirmed by) stores a user ID.
- A shared repository layer applies the workspace filter to every query. A test proves that rows belonging to a second workspace are invisible.
- The audit log records, with who, what, which record, the before and after values, and the time:
  - fact changes, AI generations and mapping confirmations;
  - approvals, rejections, previews, publishes and blocked writes;
  - exports, imports, panel actions and settings changes.

## 4. Data model

Every table has an identifier, a created time and an updated time. Workspace-owned tables also carry the workspace ID.

### 4.1 Global reference tables (shared by all workspaces)

| Table | Holds |
|---|---|
| Channel | The three marketplaces: code and display name |
| Channel category | Each marketplace category: external identifier, name, full path, parent, whether it is a leaf, the raw source record, the source and its version, last sync time |
| Channel attribute definition | Each field a marketplace category accepts (see the field details below) |
| Master attribute | ListingPilot's canonical vocabulary: key, label, data type, unit kind (length, weight, volume, count or none), description, whether it is a core field |
| Attribute map | Links a master attribute to a channel attribute definition, with a transform (identity, millimetres to centimetres, millimetres to inches, grams to kilograms, paise to rupees, comma join, yes/no from boolean, or a text template), its arguments, confidence and who confirmed it |
| Value map | Links a master value to a marketplace's exact allowed value, with confidence and confirmer. The workspace ID is optional: empty means a global mapping |
| HSN and GST | HSN code, description, GST rate, and an optional price threshold with the rate that applies above it |
| Meesho template | Category identifier, version, type, experiment flag, variant, category path, sheet name, header row, marker row, first data row, stored file, file fingerprint, source (bundled, panel download or upload), verification date, status |
| Flipkart template | Vertical, version, sheet name, header row, marker row, first data row, stored file, fingerprint, source, status (active or unsupported layout) |

**Channel attribute definition fields:**

- the owning category (empty means the field applies to the whole marketplace);
- attribute key, label and description;
- data type: text, number, whole number, yes/no, single choice, multiple choice, object or web address;
- allowed values, stored exactly as the marketplace spells them, including its typos;
- requirement level: required, conditional, recommended or optional;
- the condition, for conditional fields;
- maximum characters, maximum bytes, minimum and maximum values, and unit;
- display group and order;
- source and source version.

### 4.2 Workspace tables

| Table | Holds |
|---|---|
| Workspace | Name and business profile: legal name, GSTIN, address, customer care contact |
| User | Display name |
| Brand | Name, trademark number, Amazon Brand Registry status, Amazon GTIN exemption note, Flipkart brand approval per vertical, whether the brand appears in Meesho's brand list |
| Compliance party | Role (manufacturer, packer or importer), name, address, town, state, six-digit pincode, phone, email |
| Product family | Family code (unique per workspace), brand, name, master category, variation theme (none, size, colour, size and colour, or custom), confirmed product flags, status |
| Variant | SKU (unique per workspace) plus the attribute groups listed below |
| Attribute value | Which family or variant it belongs to; the attribute key (a master key, or a marketplace-native key for unmapped fields); the value; unit; source (manual, import, AI or marketplace); confidence; who verified it and when |
| Channel assignment | Product family, marketplace, marketplace category, how it was suggested (AI, rule or manual), confidence, who confirmed it and when |
| Media asset | Family, optional variant, role (main, alternate, packaging front, packaging back, ISI mark, size chart, swatch), position, stored file, fingerprint, width, height, format, colour mode, check results |
| Media rendition | Source asset, marketplace, stored file, public address, width, height |
| Media channel link | Source asset, marketplace, the external link the marketplace generated, status (pending, linked or invalid), source (pasted or captured by the panel worker) |
| Price offer | Variant, marketplace, selling price, Meesho wrong/defective return discount, sale price, sale start and end |
| Listing draft | Variant, marketplace, title, item highlights, bullets, description, keywords, extra fields, rule results, readiness score, status, who approved and when, AI details (model, prompt version, facts used), stale flag |
| Channel listing | Variant, marketplace, marketplace SKU, external identifier, status, last request and response (with secrets removed), issues, submission identifier, payload fingerprint, last sync time, live product address, whether ListingPilot created it |
| Export batch | Marketplace, template, file, checklist, status (generated, uploaded, results imported), upload mode (manual or panel), row count |
| Export row | Batch, variant, row number, whether held back and why, result status and message |
| Import run | Kind (catalogue, Meesho processed file, Flipkart listings report, Amazon existing listings), file, summary, row errors |
| Panel session | Marketplace, status (valid, expired, needs human login, blocked), last check time, last error |
| Job | Type, status (queued, running, succeeded, failed, cancelled, blocked), progress, inputs, result, error, idempotency key |
| Setting | Key and value: brand voice, banned claims, rule overrides, AI confidence threshold, allowed Meesho image hosts and similar |
| Audit event | User, action, record type and identifier, before and after values |

**Variant attribute groups:**

| Group | Fields |
|---|---|
| Identity | GTIN, GTIN type, GTIN status (GS1, exempt or none) |
| Variant axes | Colour and colour code, size and size code, size system |
| Tax and price | HSN, GST rate, MRP, cost |
| Stock | Stock level |
| Weights | Net weight, packed weight |
| Dimensions | Packed length, width and height; item length, width and height |
| Net quantity | Net quantity and unit |
| Compliance | Country of origin; manufacturer, packer and importer (links to compliance parties); month of manufacture; expiry date; shelf life |
| Other | Whether ListingPilot created it; status |

### 4.3 Constraints

- A SKU is unique within a workspace.
- Each variant has at most one draft and one listing per marketplace.
- A marketplace SKU is unique within a workspace and marketplace.
- Each job idempotency key is unique.

## 5. Category-agnostic attribute system

Nothing about any specific category is written into the code. Forms, rules and exports are all driven by the reference tables in section 4.1.

### 5.1 The three layers

| Layer | What it contains | Where it comes from |
|---|---|---|
| Core | Fields every marketplace needs: identity, facts, variant axes, pricing, tax, stock, logistics, compliance, media | Seeded by migration from section 5.5 |
| Marketplace-level | Fields that belong to a marketplace rather than a category: Amazon fulfilment channel and handling time; Flipkart procurement type, dispatch time, shipping provider and local, zonal and national shipping fees; Meesho wrong/defective return discount | Seeded as attribute definitions with no category |
| Category | Every field a specific marketplace category accepts | Ingested from the marketplace (section 5.2) the first time a family is assigned to that category, then refreshed weekly |

### 5.2 Ingestion per marketplace

**Amazon**

1. Search for product types for the Amazon.in marketplace, optionally by keyword.
2. For a chosen product type, request its definition with the seller identifier, the full listing requirement set and the English (India) locale. The seller identifier makes Amazon include seller-specific values such as approved brands.
3. Download the linked JSON schema and store it, keyed by product type and version.
4. Flatten the schema into channel attribute definitions:
   - each top-level property becomes an attribute;
   - properties in the schema's required list become required;
   - properties required only under conditions become conditional, with the condition stored;
   - allowed values become the allowed-value list;
   - maximum length and maximum byte length are recorded.
5. Keep the full schema for complete local validation before publishing.

**Meesho**

1. Compile every template found in the bundled templates folder, in storage, or downloaded by the panel worker. For each template, read:
   - the category path in the first row;
   - the marker row with "Compulsory Field" and "Optional Field" labels;
   - the header row with field names and descriptions;
   - the first data row;
   - the validation sheet with exact allowed values;
   - the hidden fingerprint in the instructions sheet: category identifier, version, type and experiment flag.
2. Load the Meesho category tree from the bundled category file into the channel category table.
3. A category without a template is shown as "template needed", with an upload button and, when automation is on, a download button.

**Flipkart**

1. Compile each vertical template.
2. Detect the header row, marker row and first data row automatically by scanning the first ten rows for marker words (mandatory, conditionally mandatory, optional) and by finding the validation sheets.
3. If detection fails, mark the template as an unsupported layout with the reason. Nothing crashes.

### 5.3 Mapping

**Attribute keys:**

1. Match exactly on a normalised key or label (lower case, punctuation removed), including a synonyms list kept as data.
2. If there is no exact match, ask the AI for a suggestion with a confidence score.
3. Suggestions at or above 0.9 confidence are applied automatically and audited. Lower ones go to the Mapping Review screen for a person to confirm.
4. Fields that remain unmapped still appear in the form and are stored under their marketplace-native key. They work for that marketplace only.

**Allowed values,** in order:

1. an exact case-insensitive match, returning the marketplace's exact spelling;
2. otherwise, the same number with or without its unit;
3. otherwise, exactly one allowed value appearing as a whole word in the master value;
4. otherwise, the Mapping Review screen.

**Brand, colour, HSN, GST rate and country of origin accept only exact or numeric matches. They are never fuzzy-matched.**

### 5.4 Dynamic form

For a product family and the marketplaces it is assigned to, the form shows three sections in order:

1. the core fields;
2. the combined category fields of all assigned marketplace categories, with duplicates merged through the attribute map;
3. the marketplace-only fields.

Each field shows:

- which marketplaces need it, as small labels;
- whether it is required, conditional or optional;
- a dropdown with the exact allowed values where there is a list;
- the unit;
- a badge showing where the value came from (manual, import, AI or marketplace) and its confidence.

Conditional fields appear only when their condition is met. Each marketplace has a completeness meter with a "what is missing" list.

### 5.5 Core attributes seeded at installation

| Group | Attributes |
|---|---|
| Identity | SKU, family code, GTIN, GTIN type, GTIN status, brand, manufacturer name, model number, model name |
| Product facts | Product name facts, generic name, item type keyword, material, colour, size, pattern, included components, target gender, age group, care instructions |
| Variants | Variation theme, colour family, size system, pack of, unit count and its type, net quantity and its unit |
| Pricing | MRP, selling price per marketplace, Meesho wrong/defective return discount |
| Tax | HSN, GST rate |
| Stock | Stock level |
| Logistics | Net weight, packed weight, packed dimensions, item dimensions, number of boxes |
| Compliance | Country of origin, manufacturer, packer, importer, customer care, month of manufacture, expiry date, shelf life, BIS licence number, IS standard number, FSSAI licence, warranty type and months, battery fields, hazardous-material fields |
| Media roles | Main, alternate, packaging front, packaging back, ISI mark, size chart, swatch |

## 6. Product flags

Flags are real-world facts about a product family. A person confirms each one; the AI may suggest them. Flag rules are stored as data and evaluated by the rule engine.

| Flag | Effect |
|---|---|
| Imported | Importer party required; country of origin must not be India |
| Pre-packed | Net quantity with unit, month of manufacture and customer care required; on Meesho, Images 1 and 2 must be the seller's packaging front and back photos |
| Contains battery | Battery type, count and composition required; Amazon battery and dangerous-goods attributes required |
| Expiry dated | Expiry date or shelf life required |
| Food | FSSAI licence, ingredients and vegetarian or non-vegetarian mark required |
| Cosmetic | Ingredients required |
| Electrical | Warranty, wattage and voltage required; BIS licence where applicable |
| QCO covered | BIS licence number, IS standard number and an ISI mark photo required |
| Licensed character | Licence document required; on Meesho, the Character field may only be set when the licence exists |
| Customisable or assorted | Blocks Flipkart export entirely |
| Wearable | Size chart, size system and target gender required |

## 7. Rule engine and readiness

### 7.1 Rule sources

When rule sources disagree, the higher one in this order wins:

1. administrator overrides set in Settings;
2. marketplace schemas and compiled templates (required fields, allowed values, lengths, byte limits);
3. the built-in rule files for global, Amazon, Flipkart, Meesho and flag rules.

### 7.2 Built-in rules

| Identifier | Rule | Severity |
|---|---|---|
| G-01 | Every required marketplace field for the assigned category is filled | Block |
| G-02 | Every choice value exactly matches an allowed value | Block |
| G-03 | MRP is greater than zero; each selling price is greater than zero and not above MRP | Block |
| G-04 | HSN has 4, 6, 8 or 10 digits and exists in the HSN table; the GST rate matches the HSN, including any price threshold | Block |
| G-05 | Compliance is complete: country of origin, manufacturer, packer, generic name, net quantity, customer care | Block |
| G-06 | No banned claims in the title, highlights, bullets or description | Block |
| G-07 | AI-sourced values below the confidence threshold have been verified by a person | Block |
| G-08 | No duplicate SKU; no duplicate title within a marketplace (block); no identical image across different families (warning) | Block or warning |
| A-01 | Amazon title is within the schema's maximum length, or 75 characters when the schema gives none | Block |
| A-02 | Amazon item highlights are within 125 characters | Block |
| A-03 | Amazon backend keywords are within the schema's byte limit (under 200 bytes on Amazon.in when the schema gives none), contain no brand names (block) and do not repeat title words (warning) | Block or warning |
| A-04 | Amazon main image is at least 1000 pixels on its longest side (block) and at least 97 percent of its border pixels are near-white (warning) | Block or warning |
| A-05 | GTIN present, or GTIN status declared as exempt | Block |
| A-06 | Each image's public address returns successfully before a live publish | Block |
| F-01 | Flipkart procurement type, dispatch time, shipping provider and shipping fees are set | Block |
| F-02 | The customisable or assorted flag blocks Flipkart export | Block |
| F-03 | All variants exist before the first Flipkart export, because Flipkart does not allow adding variants later | Block |
| MV-01 to MV-20 | The Meesho rules in section 10.5 | As listed there |

### 7.3 Output and timing

Each check produces:

- a list of issues, each with rule identifier, severity, marketplace, field, message and a fix hint;
- a readiness score for each marketplace: filled required fields divided by all required fields, shown as a percentage;
- a blocking flag.

Rules run on every save, generation, edit and import. When a fact changes, every draft that depends on it is marked stale.

## 8. AI

### 8.1 Providers

| Provider | Use |
|---|---|
| Anthropic provider | Calls the Anthropic Messages API with the configured model |
| Fake provider | Deterministic, for tests only |
| Deterministic generator | Writes copy from facts only; used when no AI key is set or the provider fails; shown in the interface with an "AI unavailable" badge |

The provider interface offers four capabilities: generate copy, suggest an attribute or value mapping, suggest marketplace categories, and suggest product flags.

### 8.2 Inputs and outputs

- **Inputs:**
  - verified and manually entered facts only;
  - the marketplace brief: limits from the live schema or template, brand voice, banned claims and style rules.
- **Output:** a structured result containing:
  - title;
  - item highlights (Amazon only);
  - five bullets;
  - description;
  - keywords;
  - the list of fact keys used.
- Any statement relying on a fact that was not supplied fails validation.

### 8.3 Validation loop

1. The rule engine checks the output.
2. If a rule fails, the generator is asked again with the specific violation stated.
3. After at most two retries, the draft is kept with its issues for the person to fix.

### 8.4 Style per marketplace

| Marketplace | Style |
|---|---|
| Amazon | Title built as brand, core product noun, top differentiator and key variant attribute, within 75 characters. Remaining searchable attributes go into item highlights. Five bullets. Backend keywords without brand names and without repeating the title |
| Flipkart | Title and key features within the vertical template's limits |
| Meesho | Product name without weight, dimensions, price, promotional words or other marketplace names. Description of two to four plain sentences with no HTML |

### 8.5 Record keeping

Every generation records the model, prompt version and facts used in the draft, and writes an audit event.

## 9. Media

- **Upload:**
  - JPEG, PNG or WebP, up to 15 megabytes, validated by content rather than file extension;
  - the original is stored unchanged with its fingerprint.
- **Checks:** pixel size, colour mode, white-border estimate, aspect ratio, duplicate detection.
- **Renditions:**

| Marketplace | Rendition |
|---|---|
| Amazon | JPEG in sRGB, at least 1000 pixels on the longest side, high quality, stored in public storage with a public address |
| Flipkart | JPEG in sRGB |
| Meesho | JPEG in RGB, at most four per SKU |

- **Meesho image package:** a ZIP containing each SKU's images named with the SKU and slot number (1 to 4).
- **Meesho link paste-back,** used when the panel worker is off:
  - The seller pastes the links the Meesho panel generated, either as lines of file name followed by link, as CSV, or as links in file-name order.
  - ListingPilot matches them by file name.
  - It rejects Google Drive, WhatsApp, localhost and non-web links.
  - It warns when a link's host is not in the allowed-hosts setting. That setting is filled with the host the real panel returns, discovered during milestone M7.

## 10. Marketplace adapters

### 10.1 The write guard

The write guard decides every marketplace write. A write is allowed only when all of the following are true:

1. the marketplace is in live mode;
2. live writes are switched on;
3. the SKU is on the allowlist, or the allowlist is a single asterisk;
4. the action is not a delete (deletes are never allowed);
5. the listing was created by ListingPilot, or its SKU is explicitly on the allowlist.

In mock mode the guard always allows, because the mock server is not a real account.

When the guard refuses a write:

- the listing status becomes "write blocked", with the reason;
- an audit event is recorded;
- the interface shows exactly what would have been sent.

Reads, Amazon validation previews and panel navigation are not writes.

### 10.2 Shared adapter behaviour

- Every adapter offers the same capabilities:
  - ensure the category schema is loaded;
  - build a payload;
  - validate;
  - publish or export;
  - sync status;
  - update offer;
  - import existing listings.
- Each marketplace has one HTTP client with:
  - timeouts;
  - retries on rate-limit and server errors, with randomised back-off;
  - request pacing.
- Amazon listing writes are paced at five requests per second with a burst of five.
- Requests and responses are stored with secrets removed.

### 10.3 Amazon (Selling Partner API)

1. **Authentication.**
   - Exchange the refresh token for an access token through Login with Amazon.
   - Reuse it until one minute before expiry.
   - A permission error naming a missing role sets the channel to "API scope missing", with the role named.
   - Required roles: Product Listing, Pricing, and Inventory and Order Tracking.
2. **Import existing listings (read).**
   - Request the merchant listings report through the Reports API and match by SKU.
   - Existing listings become channel listing records marked as not created by ListingPilot, with status live or inactive as reported. The master then reflects the seller's real Amazon catalogue without changing it.
3. **Schema.** Loaded as in section 5.2. Payloads are validated locally against the full schema, including Amazon's byte-length limits, before any call.
4. **Catalogue match first.**
   - Search the Amazon catalogue by GTIN.
   - If a product already exists, propose an offer-only listing on that ASIN. The seller confirms.
   - This prevents duplicate ASINs.
5. **Payload.** A Listings Items document containing:
   - mapped master values and the approved draft copy;
   - image public addresses;
   - the offer (selling price, list price equal to MRP, quantity).
6. **Validation preview.**
   - Submit the payload with Amazon's validation-preview mode.
   - Amazon returns issues without creating anything; each issue is shown against its field.
   - No guard is needed.
7. **Publish,** through the write guard.
   - An accepted response stores the submission identifier and sets the status to submitted.
   - An invalid response sets "needs fix", with the issues.
8. **Polling.**
   - A job reads the listing every two minutes for two hours, then hourly for up to 48 hours.
   - When an ASIN appears it is stored.
   - When the status shows the item as buyable, the listing is live.
   - When error-level issues appear, it is "needs fix".
9. **Price and stock.**
   - A partial update changes only the offer and fulfilment availability, through the write guard.
   - Polling confirms the new values.

### 10.4 Flipkart (Seller API)

1. **Authentication.**
   - Client-credentials token from the self-access application's identifier and secret.
   - A missing permission sets "API scope missing", naming the scope.
   - The Listings scope is required.
2. **Sync existing listings (read).**
   - Use the listing search call, which returns all of the seller's listings with FSN and SKU in pages of 500, following the next-page marker until no more remain.
   - Fetch details for SKUs in batches of up to ten where needed.
   - Fall back to importing the Seller Hub listings report if the API cannot return everything.
   - Synced listings are marked as not created by ListingPilot.
3. **Update existing listings (existing FSN only).**
   - Use the version 3 listing calls for price, stock, tax (HSN and Flipkart tax code), fulfilment (procurement type, dispatch time, shipping provider), packages, locations and Legal Metrology address labels.
   - Flipkart's create call overwrites any listing with the same SKU. Every update therefore needs confirmation in the interface, showing the difference from the last payload, and passes through the write guard.
4. **New products.**
   - Fill the compiled vertical template into a copy of the original file, writing only data rows.
   - Hold back invalid rows with reasons.
   - The seller uploads the file in Seller Hub; there is no Flipkart panel automation.
   - The new FSN arrives at the next sync.
5. **No templates.** When no vertical templates exist, the Flipkart page explains how to add them in Settings. Tests use synthetic templates.

### 10.5 Meesho: file pipeline (always available)

1. **Template selection.** The master category narrows the candidates by category path. The seller confirms the template, and the choice is stored on the channel assignment.
2. **Identifiers:**
   - Style ID: family code and colour code, so it is the same across sizes and different across colours.
   - SKU ID: the variant SKU.
   - Group ID: the family code.
3. **Filling:**
   - Copy the original template and write only data rows, starting at the first data row.
   - Identifiers, pincodes, EAN and HSN are written as text; numbers as numbers.
   - Choice fields receive only exact allowed values.
   - The AI never writes into the sheet directly.
4. **Images.** Image cells receive the marketplace links from the media channel link table. Export is blocked while any row lacks Image 1.
5. **Rules.** All block unless marked as warnings.

| Identifier | Rule |
|---|---|
| MV-01 | Every compulsory column is filled |
| MV-02 | Every choice value exactly matches the validation sheet, including Meesho's own spellings |
| MV-03 | Meesho price is below MRP; MRP is above zero |
| MV-04 | If a wrong/defective discount is set, it is above zero and the resulting price is above zero and below the Meesho price |
| MV-05 | HSN appears in the template's list; GST rate is consistent with it |
| MV-06 | Pincodes have six digits; addresses include town or district and state |
| MV-07 | If the country of origin is not India, real importer details are present |
| MV-08 | SKU ID is unique within the file and across all previous exports |
| MV-09 | Style ID is the same across sizes of one colour and different across colours |
| MV-10 | One category per Group ID (block); fewer than three products in a group (warning) |
| MV-11 | Image 1 is present and its link passes validation |
| MV-12 | Image quality checks (warning) |
| MV-13 | Product name contains no weight, dimensions, price, other marketplace names or restricted words |
| MV-14 | Pre-packed products have packaging photos as Images 1 and 2 |
| MV-15 | QCO-covered products have a BIS licence number, IS standard number and an ISI mark photo |
| MV-16 | A character other than "Not Applicable" has a licence on file |
| MV-17 | EAN has 13 digits |
| MV-18 | Size measurements exist for every size row and fall within the allowed range |
| MV-19 | Product description is present (warning) |
| MV-20 | The template was verified more than 30 days ago (warning) |

6. **Export package.** A ZIP with one filled template per category and a checklist naming:
   - the exact panel category path to select;
   - row counts;
   - held-back rows with reasons;
   - a reminder to bring back the processed file.
7. **Processed-file import.**
   - Read the error status and error message columns; match rows by SKU ID and template version.
   - Rows with errors become "needs fix", with the message mapped to a field by column name or keywords.
   - Clean rows become "uploaded, awaiting live". They become live when the panel worker sees them live, or the seller marks them live.
   - A correction sheet containing only failed rows is offered.

### 10.6 Meesho: panel automation (P1, only when MEESHO_AUTOMATION is true)

The panel worker uses a real browser on the seller's own account, one job at a time.

**Session.**

1. Session-first: the worker always loads the saved session file first.
2. The first session is created by a person running the one-time login command, which opens a visible browser for a normal login, including any OTP.
3. If the saved session is missing or expired, the worker may try one scripted password login per day, using the .env login.
4. If that login shows an OTP prompt, a captcha or any unexpected screen, the worker:
   - stops and saves a screenshot;
   - sets the panel session to "needs human login";
   - blocks all panel jobs;
   - shows a banner asking for the one-time login command.
5. Any redirect to the login page counts as session expiry.

**Pace and safety.**

- Random waits of two to six seconds between actions.
- Selectors live in one place, each with fallbacks: accessible role or test identifier first, then visible text, then structure.
- On any unexpected page, the worker stops, saves a screenshot, marks the job blocked with the reason, and offers the manual path.
- The worker only ever submits files ListingPilot generated.

**Operations.**

| Operation | Type | What it does |
|---|---|---|
| Discover | Read | Navigates the catalog upload area once during milestone M7, recording screenshots and selectors into docs/meesho/PANEL_MAP.md, with personal data removed |
| Download template | Read | Selects the category in the bulk catalog flow, downloads its template and sends it to the compiler |
| Upload images and capture links | Guarded write | Uploads the SKU images through the panel's bulk image upload, captures the generated links and maps them to SKUs by file name |
| Upload sheet | Guarded write | Selects the exact category path from the checklist and uploads the generated file |
| Sync QC | Read | Reads catalog QC statuses, downloads error files and passes them to processed-file import |

**Fallback.** If any automated step fails, the same step is offered manually in the wizard, with the generated files ready.

## 11. Listing states (per variant and marketplace)

### 11.1 Main path

1. Not started
2. Draft
3. Approved
4. Validated (Amazon only, after a clean preview)
5. Submitted (Amazon or Flipkart API) or Exported (Meesho or Flipkart file)
6. Uploaded, awaiting QC (files)
7. Uploaded, awaiting live
8. Live

### 11.2 Side states

| State | Meaning |
|---|---|
| Needs fix | Issues from rules, the marketplace or a processed file |
| Write blocked | The write guard refused |
| API not connected | Credentials missing |
| API scope missing | A role or scope is missing |
| Needs human login | The Meesho session needs a person |
| Stale | A fact changed after approval |
| Inactive | Reported inactive by the marketplace |

### 11.3 Transition rules

- Editing an approved draft returns it to Draft.
- Publish or export requires Approved and no blocking issues; the server enforces this.
- A failure or a blocked write never produces Live.

## 12. Background jobs

### 12.1 Job types

| Area | Jobs |
|---|---|
| AI | Draft generation in batches, with per-item progress and cancellation |
| Amazon | Schema sync, existing-listing import, validation preview, publish, polling, offer update |
| Flipkart | Existing-listing sync, offer update |
| Files | Export building, file import, template refresh |
| Meesho panel | Session check, template download, image upload, sheet upload, QC sync |

### 12.2 Rules

- **Idempotency:** every job has a key made from its type, record and a fingerprint of its inputs. A retry skips steps already completed.
- **No double submissions:** the same payload for the same variant and marketplace is never submitted twice.
- **Visibility:** the jobs drawer shows progress, errors, Retry and Cancel.

## 13. REST API

All paths are under /api/v1. Errors return a code, a message and details.

| Area | Endpoints |
|---|---|
| Session | Log in with the shared password; log out |
| Health | Live checks of database, Redis, storage, public media address, AI, Amazon token and role probe, Flipkart token, Meesho session, and the mock server in mock mode |
| Setup | Read and update the workspace; create, read, update and delete brands and compliance parties |
| Catalogue | Create, read, update and delete families and their variants; get the dynamic form for chosen marketplaces; save attribute values; get readiness |
| Taxonomy | Search marketplace categories; suggest and confirm channel assignments; list and confirm pending mappings |
| Import and export | Download the catalogue template; import a catalogue file; read an import run's results; export the catalogue as Excel, CSV or JSON |
| Media | Upload to a family; update or remove an image; download the Meesho image package; submit pasted Meesho links |
| Drafts | Start generation (as a job); list; read; edit; approve; reject |
| Amazon | Import existing listings; catalogue match; validation preview; publish; offer update; schema sync |
| Meesho | Build an export (refused with a list of problems when blocked); download; upload through the panel or mark as manually uploaded; import a processed file; download a correction sheet; read and check the session; download a template through the panel |
| Flipkart | Sync existing listings; build a template export; import a listings report; offer update |
| Status | Status grid; report summary; audit log; jobs list and detail; cancel and retry jobs |
| Settings | Read and update settings; upload and list templates; read the write-guard status (mode, on or off, allowlist size; never secrets) |

The API publishes an OpenAPI description. The web app uses a typed client generated from it.

## 14. Screens

| Screen | Contents |
|---|---|
| Login | Shared password |
| Setup | First-run wizard: profile, brands, compliance parties, connection status, write-guard status |
| Catalogue | Paged grid of families and variants with search, filters and readiness labels per marketplace; bulk actions; import and export |
| Family | Tabs for details (dynamic form with completeness meters), variants (matrix), media, marketplaces (category assignment), drafts, listings and history |
| Mapping review | Pending attribute and value mappings to confirm or edit |
| Drafts | Queue by status; per-marketplace editor with live character and byte counters; issue list; approve and reject |
| Amazon | Existing-listing import, catalogue match, preview issues, publish, live status, offer update |
| Meesho | Session status; step-by-step wizard (select products, images, links, export, upload, QC sync); processed-file import; correction sheet |
| Flipkart | Existing-listing sync, template export, listings-report import, offer update with difference confirmation |
| Status | Grid of SKUs by marketplace with real states and identifiers; each cell opens the screen where it can be fixed |
| Reports | Counts, readiness, acceptance and rejection rates calculated from the database |
| Audit | Searchable event list |
| Settings | Brand voice, banned claims, rule overrides, templates, connections, write guard, AI confidence threshold, allowed Meesho image hosts |
| Health | Live dependency checks |

**Global elements on every screen:**

- the mock banner or the live-writes banner;
- notifications that appear only after the server confirms the outcome;
- the jobs drawer;
- empty states that explain the next step.

## 15. Security and deployment

- The shared password gate uses signed session cookies and limits login attempts.
- Secrets never reach the browser, logs, audit values, test evidence or screenshots. Redaction plus a scanning test enforce this.
- The .env file, the secrets folder and the pilot data folder are excluded from version control.
- The application runs locally or on a private server reachable only through a VPN or an IP allowlist. It is never exposed publicly before the SaaS phase adds proper authentication.

## 16. Non-functional requirements

| Area | Requirement |
|---|---|
| Speed | Copy for all three marketplaces for one SKU in under 30 seconds (95th percentile, real AI); a 500-row Meesho export in under 60 seconds; a 5,000-variant grid paged by the server |
| Reliability | Idempotent jobs; no double submissions; panel jobs strictly one at a time |
| File fidelity | Exported templates are identical to the originals except in data cells, including sheets and dropdown validations; proven by golden-file tests |
| Observability | Structured logs; per-marketplace error counts on the Health and Reports screens |

## 17. Glossary

| Term | Meaning |
|---|---|
| ASIN | Amazon's product identifier |
| FSN | Flipkart's catalogue product identifier |
| LID | Flipkart's listing identifier for a seller's offer |
| SP-API | Amazon Selling Partner API |
| Self Access Application | Flipkart's API application type for a seller's own use |
| Product type definition | Amazon's machine-readable requirements for a product type |
| Style ID / Group ID | Meesho identifiers grouping sizes and catalogs |
| Write guard | ListingPilot's protection that decides every real marketplace write |
| Master catalogue | ListingPilot's single source of product facts |