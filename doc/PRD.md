# ListingPilot — Product Requirements Document

Version 2.1 · Thursday 29 October 2026

## 1. Overview

| Item | Detail |
|---|---|
| Product | ListingPilot: a master catalogue and listing automation system for Indian marketplaces |
| Marketplaces | Amazon.in, Flipkart, Meesho |
| MVP mode | One seller: one workspace, one operator, no login beyond a shared password |
| Future mode | Multi-tenant SaaS for many sellers; the data model is ready for this from day one |
| Credentials | One real seller's Amazon, Flipkart and Meesho credentials, held in the .env file until the SaaS phase |
| Start date | Thursday 29 October 2026 |
| Deadline | Friday 20 November 2026 |
| Builder | Claude Code, working autonomously under CLAUDE.md |

## 2. Summary

Indian sellers maintain the same product three times: once in Amazon's schemas, once in Flipkart's vertical templates and once in Meesho's category templates. Each marketplace has different fields, different limits and different rejection behaviour. A fix made in one portal rarely reaches the others.

ListingPilot is the single master catalogue for every product. The seller enters facts once and works only inside ListingPilot. For each marketplace, ListingPilot:

1. maps the product to that marketplace's category;
2. shows exactly which fields the marketplace needs and what is missing;
3. writes marketplace-specific copy with AI, using only the product's facts;
4. checks everything against the marketplace's current rules before anything is sent;
5. publishes through the best official route available;
6. brings back real identifiers, statuses and rejection reasons, mapped to the fields that caused them.

The central principle is **facts in the master, expression in the channel**:

- **Facts** live only in the master catalogue and are never invented by AI. Examples: dimensions, material, MRP, compliance declarations, GTIN, tax codes.
- **Expression** is generated separately for each marketplace from those facts. Examples: titles, highlights, bullets, descriptions, keywords.

## 3. Problem

| Pain | Effect |
|---|---|
| Triple data entry | Hours per SKU across three portals; effort grows with every new product |
| Different and changing rules | Amazon now limits titles to 75 characters and adds a 125-character Item Highlights field; backend keywords on Amazon.in must stay within a byte limit; Flipkart and Meesho each have their own templates and mandatory fields |
| Opaque rejections | Flipkart and Meesho quality-check messages are often generic; sellers retry blindly |
| Compliance burden | Legal Metrology declarations, BIS/QCO marks, FSSAI licences and GST data must be correct on every listing on every marketplace |
| Hidden economics | On Meesho, declared weight drives shipping cost and therefore margin |
| No single source of truth | Each portal drifts from the others; nobody knows which version is correct |

## 4. Market position

Research of tools available to Indian sellers in 2026 shows three groups. None combines a category-agnostic master catalogue, compliance data, schema-driven validation, real API publishing and a rejection feedback loop.

| Group | Examples | Strength | Gap ListingPilot fills |
|---|---|---|---|
| Order and inventory systems | Unicommerce, EasyEcom, Vinculum, Marketplace Mitra, Robnu | Orders, stock and warehouses across many channels | Catalogue features are operational, not a true product information system; they do not help with Meesho catalog creation or approval |
| AI listing generators | AutoList AI, Sellermitra, SellerShip, ListSync AI | Fast copy writing and filled bulk templates; some publish to Amazon | Little compliance handling, no schema-driven validation, no rejection loop, no single source of truth |
| Meesho browser extensions | EcomFriendly, InfigrowAI, Meesho Autofill | Autofill the Meesho panel inside the seller's own browser session | Single marketplace; no master catalogue; no validation |

**ListingPilot's position:** the correctness layer between a seller's product data and all three marketplaces.

- **Correct:** schema- and template-driven rules, compliance enforced.
- **Complete:** per-marketplace completeness for any category.
- **Honest:** real statuses only.
- **Connected:** official APIs where they exist, official templates where they don't.

## 5. Users

| User | MVP | Description |
|---|---|---|
| Seller-operator | Primary | One person who maintains the catalogue, reviews and approves listings, fixes rejections and handles Meesho uploads when automation is off |
| Catalogue executive at a brand | Supported as the same single operator | Manages hundreds to thousands of SKUs |
| Agency managing many brands | Deferred to the SaaS phase | Needs workspaces, roles and approvals |

## 6. Goals

1. One master catalogue that works for any category on all three marketplaces without code changes.
2. Per-marketplace completeness, so the seller always knows what is missing and why.
3. Rule checks before submission, not rejections after.
4. Compliant, consistent AI copy that respects each marketplace's current limits.
5. The seller never opens a marketplace portal for routine listing work.
6. The real seller account is protected by a write guard, human approval, no destructive actions and paced automation.
7. The seller owns all data and can export the full catalogue at any time.

## 7. Non-goals for the MVP

- Login, multiple users, roles, maker-checker approvals and agency mode (SaaS phase).
- A per-tenant encrypted credential vault; credentials stay in .env until the SaaS phase.
- AI image generation, the Meesho shipping optimiser, the returns advisor, A+ content publishing and Hindi or regional-language content.
- Orders, shipping labels, returns handling, advertising, repricing and accounting.
- Meesho's partner API. It is partner-gated, mainly covers orders and inventory, and once enabled it disables order acceptance, manifesting and cancellation inside the Meesho panel. It is a SaaS-phase decision.
- Automating the Flipkart seller panel.
- Marketplaces other than the three named.

## 8. Product principles

1. **Facts in the master.** AI never invents facts; every AI sentence is traceable to supplied facts.
2. **Rules are data.** Limits and requirements come from Amazon's live schemas, compiled marketplace templates and editable rule sets, never from hard-coded numbers.
3. **Deterministic validation wraps AI.** Code checks every AI output before a person or a marketplace sees it.
4. **Honesty.** The screen shows only what really happened.
5. **Humans own legal, safety and money decisions.** Compliance data, prices, GTIN status and final approval belong to the seller.
6. **The seller account is sacred.** Write guard, rate limits, no deletes, no changes to listings the system didn't create, human-paced panel automation.

## 9. Core user journey

### Stage 1: Setup

The seller completes a first-run wizard, editable later in Settings:

- business profile: legal name, GSTIN, address, customer care contact;
- brands;
- compliance parties: manufacturers, packers and importers with addresses and pincodes;
- a review of the live connection status of each marketplace.

The wizard also shows the write-guard status: whether live writes are on, and for how many SKUs.

### Stage 2: Bring in products

The seller either imports the existing catalogue (Excel or CSV) or creates products in a form. For each product family, the seller:

1. chooses a master category;
2. confirms ListingPilot's proposed Amazon product type, Flipkart vertical and Meesho template;
3. fills a dynamic form, built from three layers:
   - **core fields** every marketplace needs;
   - **category fields** drawn from the marketplaces' own schemas and templates;
   - **marketplace-only fields.**

A completeness meter for each marketplace lists what is still missing. The seller can also pull in existing listings from Amazon and Flipkart, so the master reflects what is already live.

### Stage 3: Media

The seller uploads photos. ListingPilot:

- checks each image against each marketplace's rules (resolution, white background, format, duplicates);
- creates marketplace-specific versions;
- never alters the originals.

### Stage 4: Generate and review

AI writes copy for each marketplace. The rule engine checks it straight away. The seller edits, sees live character and byte counters, and approves. Approval is refused while blocking issues remain.

### Stage 5: Publish

- **Amazon:** search the Amazon catalogue first to avoid duplicates, run a validation preview against Amazon's real rules, publish, then poll until the real ASIN and status come back.
- **Flipkart:**
  - **Existing catalogue products (FSN):** price, stock and listing details are updated through the API.
  - **New products:** ListingPilot produces the filled vertical template for upload; the FSN is synced back afterwards.
- **Meesho:** ListingPilot prepares images and a filled official template.
  - **With panel automation on:** it uploads the images, captures the generated links, uploads the sheet and reads the QC result through the seller's own saved session.
  - **With automation off, or if it fails:** the seller is guided through the same steps manually.

### Stage 6: Fix and resend

Rejections and issues come back from each marketplace mapped to the exact field. The seller fixes the fact once in the master, and every affected marketplace draft is flagged for regeneration.

### Stage 7: Track

- A status hub shows every SKU on every marketplace with real states and identifiers.
- Reports show coverage, readiness, acceptance and rejection rates calculated from the database.
- An audit log records every important action.

## 10. Features

| ID | Feature | Description | Priority |
|---|---|---|---|
| F1 | Setup | Business profile, brands, compliance parties, live connection status, write-guard status | P0 |
| F2 | Master catalogue | Product families and variants with identity, pricing, tax, stock, logistics and compliance data | P0 |
| F3 | Category-agnostic attributes | Marketplace schemas and templates ingested into the database; master attribute dictionary; attribute and value mappings with review; dynamic forms | P0 |
| F4 | Product flags | One-time real-world flags (imported, pre-packed, battery, food, QCO and others) that drive conditional requirements | P0 |
| F5 | Import and export | Excel and CSV import with row-level errors; full catalogue export at any time; pilot data import | P0 |
| F6 | Media | Image checks, marketplace renditions, public storage for Amazon, Meesho image ZIP and link capture | P0 |
| F7 | AI copy | Per-marketplace titles, highlights, bullets, descriptions and keywords, grounded in facts and validated | P0 |
| F8 | Rule engine | Schema-, template- and rule-file-driven checks with a readiness score per marketplace | P0 |
| F9 | Review and approval | Edit, re-check, approve or reject, with the approval gate enforced by the server | P0 |
| F10 | Amazon | Schema download and local validation, validation preview, catalogue match, publish, ASIN polling, price and stock updates, existing-listing import | P0 |
| F11 | Meesho file pipeline | Template compiler, filling, the twenty Meesho rules, export package with checklist, processed-file import and correction sheet | P0 |
| F12 | Meesho panel automation | Saved-session login, template download, image upload with link capture, sheet upload, QC sync | P1, behind a flag |
| F13 | Flipkart | Existing-listing sync via listing search, API updates for existing FSNs, template export for new products | P1 |
| F14 | Operations | Status hub, reports, audit log, real health page, background jobs with progress | P0 |
| F15 | Settings | Brand voice, banned claims, rule overrides, template management, connection status, write-guard status, AI confidence threshold | P0 |
| F16 | Write guard and live-run report | Protection for the real seller account and a record of everything really done on it | P0 |

## 11. How each marketplace is integrated

### MVP: one seller

| Marketplace | Route | Notes from research |
|---|---|---|
| Amazon.in | Selling Partner API with a private, self-authorised application | Needs a professional selling account; registered by the primary account user; developer approval is typically a few business days; roles needed: Product Listing, Pricing, and Inventory and Order Tracking |
| Flipkart | Seller API through a Self Access Application created by the seller under Manage Profile, then Developer Access, using client credentials. Upload templates for new products | The API listing call requires an existing Flipkart catalogue ID (FSN), so brand-new products need the template. A listing search call returns all listings with FSN and SKU in pages of 500. Flipkart states self-access details must not be shared with third-party aggregators |
| Meesho | Official category templates, uploaded either by the panel worker using the seller's saved session or by the seller | Public guides checked in October 2026 report a password-first login with an OTP fallback. The first login is done once by a person; later runs reuse the saved session. Meesho's API is partner-only and does not create catalogs |

### SaaS phase: many sellers

| Marketplace | Change |
|---|---|
| Amazon | Register as a public developer and list the application in the Selling Partner Appstore. Sellers authorise through OAuth. Developers report public registration reviews taking several weeks, so apply early |
| Flipkart | Register a third-party application, which uses the authorisation-code flow and requires Flipkart's verification. The self-access model cannot be used for other sellers |
| Meesho | Replace server-side panel automation with a ListingPilot browser extension that works inside each seller's own logged-in session, so ListingPilot never stores Meesho passwords. This is the model existing Meesho tools use. Separately, apply to Meesho's integration programme for stock sync, after explaining the order-handling trade-off to each seller |
| Credentials | Move from .env to a per-workspace encrypted vault; only the credential-access function changes |
| Users | Add login, roles, maker-checker approvals and per-user audit |

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Accidental changes to the real seller's live listings | Wrong prices, wrong listings, account health damage | Write guard with allowlist, no deletes, no changes to foreign listings, previews by default, live-run report |
| Meesho panel automation conflicts with Meesho's terms or is flagged | Account warning or block | Off by default; seller's own session; human pace; stops on anything unexpected; manual path always available. No explicit Meesho rule either way was found; Meesho's terms say third-party tools are used at the user's own risk |
| Meesho login asks for an OTP or captcha | Panel jobs cannot run | Honest "needs human login" state; one-time login command; saved session reuse |
| Missing API roles or scopes | Calls fail | Honest "API scope missing" state naming the role; handoff instructions |
| Marketplace rules change | Rejections | Limits come from live schemas and compiled templates; rejection imports; template freshness warnings |
| Template layouts differ per seller (Meesho A/B tests) | Upload failures | Templates downloaded from the seller's own panel; fingerprint stored and checked |
| Credentials in a plain .env file and a shared app password | Credential exposure | Private deployment only (VPN or IP allowlist); secrets never logged; vault in the SaaS phase |
| Single autonomous builder with a fixed deadline | Scope slip | Clear cut order; safety, honesty and tests are never cut |

## 13. Success criteria

### Build complete on 20 November

- Every item in the BUILD_PLAN definition of done is checked.
- The full green gate passes.
- The live-run report is written.

### Pilot outcomes, measured per seller after go-live

| Metric | Target |
|---|---|
| Median time from new master product to ready on all three marketplaces | Under 10 minutes per SKU |
| Amazon first-submission acceptance | At least 90 percent |
| Meesho and Flipkart first-upload acceptance | At least 80 percent |
| AI-written fields accepted without edits | At least 70 percent |
| AI factual errors in an audit sample | Under 1 percent |

## 14. Assumptions

- The owner supplies valid credentials and, ideally, pilot data before the build starts.
- The seller has a professional Amazon account and an active Flipkart seller account with a self-access application created.
- The seller accepts the Meesho automation risk before panel automation is switched on.
- The application runs locally or on a private server; it is never publicly reachable before the SaaS phase adds proper authentication.