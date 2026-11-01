# ListingPilot — Specification Addendum

This addendum fills every gap left open by the PRD and SRS. Where it differs from the SRS, the TEST_PLAN or the HUMAN_HANDOFF, this addendum wins.

## 1. Importing the seller's own spreadsheet

The seller's catalogue will not match ListingPilot's template. Import therefore always goes through a mapping step.

### 1.1 Import flow

1. **Upload.** The seller uploads an Excel or CSV file. For Excel files with several sheets, the seller picks the sheet, and ListingPilot proposes the first sheet containing a column that looks like a SKU.
2. **Header detection.** ListingPilot finds the header row by scanning the first ten rows for the row with the most non-empty text cells.
3. **Column mapping.** Every source column is shown with a suggested target:

   | Suggestion step  | How it works                                                                                   |
   | ---------------- | ---------------------------------------------------------------------------------------------- |
   | 1. Saved mapping | A mapping saved from an earlier import of a file with the same headers                         |
   | 2. Exact match   | A match on normalised header names against master attribute keys, labels and the synonyms list |
   | 3. AI suggestion | A suggestion with confidence for anything left                                                 |

   Each target is a master attribute, a variant field, a family field, a compliance party field, an image column, or "ignore". Unmatched columns default to "keep as attribute", stored under the original header name.

4. **Units and transforms.** For each numeric column, the seller picks the source unit:
   - **Weights:** grams or kilograms.
   - **Lengths:** millimetres, centimetres or inches.
   - **Money:** rupees.

   ListingPilot suggests the unit from the header text, for example "(kg)" or "in cm".

5. **Family grouping.** The seller picks how rows form product families:
   - by a chosen column, such as a style or parent code;
   - by the SKU with its last segment removed;
   - each row as its own family.

   The default is a parent or style column if one is mapped. Otherwise each row becomes its own family.

6. **Preview.** The first 20 rows are shown as they will be stored, with row-level errors and warnings.
7. **Import.** Created, updated and failed counts are shown, with a downloadable error report listing row number, column, value and reason.
8. **Save mapping.** The mapping is saved under the file's header fingerprint for reuse.

### 1.2 Compliance parties from spreadsheets

Manufacturer, packer and importer columns are matched to existing compliance parties by name and pincode. New parties are created when no match exists, and listed in the import summary for review.

### 1.3 Photos

Photos in data/pilot/photos, or in an uploaded ZIP, are matched to SKUs by file name:

- the file name must start with the SKU, followed by an optional underscore and a position number;
- position 1, or no number, becomes the main image;
- higher numbers become alternate images in order;
- file names that match no SKU are listed in the import summary.

Image web addresses in spreadsheet columns are downloaded during import, through the same checks as uploads. Failures are listed per row.

### 1.4 Family codes

When the seller's data has no family code, ListingPilot generates one:

- the common prefix of the family's SKUs if it is at least four characters;
- otherwise a short code from the product name.

Codes are upper-case letters, digits and hyphens, unique per workspace and editable.

## 2. GST and HSN data policy

ListingPilot never invents tax data.

- The HSN and GST table starts empty.
- It is filled only from:
  - **the seller's own data,** as imported HSN and GST values: marked "seller-supplied" and treated as verified;
  - **marketplace templates,** such as the HSN lists inside Meesho templates: HSN codes only, without rates, marked "template";
  - **manual entries** in Settings: marked "verified".
- An HSN without a known rate cannot pass rule G-04. The issue tells the seller to enter the rate.
- Claude Code must not seed GST rates from memory or from the web.

## 3. Live testing settings and cleanup

### 3.1 Test SKUs

One more .env setting, LIVE_TEST_SKUS, lists SKUs that exist purely for testing. They must also appear in the write allowlist.

| SKU type                                         | Treatment                                           |
| ------------------------------------------------ | --------------------------------------------------- |
| Real allowlisted SKUs (allowlist, not test list) | Published and left live, like normal production use |
| Test SKUs                                        | Cleaned up at the end of each live test             |

### 3.2 Cleanup of test SKUs

| Marketplace | Cleanup action                                                                                                                                                                                                       |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Amazon      | Stock set to zero; the listing is never deleted                                                                                                                                                                      |
| Flipkart    | Any changed price or stock restored to its value before the test; listings created by the test are set to inactive                                                                                                   |
| Meesho      | The live-run report lists the uploaded test catalogs, because Meesho stock changes require the panel. If panel automation is on and the session is valid, stock is set to zero through the panel, as a guarded write |

Every cleanup action is recorded in the live-run report.

### 3.3 If the test list is empty

No cleanup runs. Live writes affect only real allowlisted SKUs.

## 4. Marketplace default settings

These defaults live in Settings. Each is first inferred from the seller's existing listings where possible, and the inference is recorded in DECISIONS.

### 4.1 Amazon

| Setting                                     | Default and inference                                                                                                                                                         |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fulfilment                                  | Merchant-fulfilled (the default fulfilment channel). Fulfilled-by-Amazon listings are never created by ListingPilot in the MVP                                                |
| Handling time                               | The most common value among imported existing listings; otherwise 2 days                                                                                                      |
| Shipping template (merchant shipping group) | The most common value among imported existing listings; otherwise left empty so Amazon uses the account default. Any validation-preview issue about it is shown to the seller |
| Condition                                   | New                                                                                                                                                                           |
| Price                                       | Selling price from the price offer; list price equals MRP                                                                                                                     |

### 4.2 Flipkart

| Setting                                 | Default and inference                                                                                                |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Procurement type                        | Regular                                                                                                              |
| Dispatch time                           | The most common value among synced listings; otherwise 2 days                                                        |
| Shipping provider                       | The most common value among synced listings; otherwise Flipkart                                                      |
| Local, zonal and national shipping fees | Most common values among synced listings; otherwise zero                                                             |
| Location                                | The seller location returned with synced listings. If there are several, the most common, and the choice is recorded |
| Tax code                                | Must come from seller data or the vertical template, never guessed                                                   |

### 4.3 Meesho

| Setting                         | Default       |
| ------------------------------- | ------------- |
| Wrong/defective return discount | Empty         |
| Inventory                       | Variant stock |

## 5. Rule files

### 5.1 Format

Rules are stored as human-readable data files in the rules folder, one file per scope: global, Amazon, Flipkart, Meesho and flags. Each rule has these fields:

| Field        | Content                                                                                                                                         |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Identifier   | Matches the SRS tables, for example G-03 or MV-11                                                                                               |
| Description  | One plain sentence                                                                                                                              |
| Marketplaces | Which marketplaces it applies to                                                                                                                |
| Scope        | Family, variant, draft, media or export row                                                                                                     |
| Condition    | Optional. When the rule applies: a flag value, a field comparison, or a combination with "all of" and "any of"                                  |
| Check        | What must be true: a field present, a comparison between fields, a length or byte limit, a pattern, membership of a list, or a uniqueness check |
| Severity     | Block or warning                                                                                                                                |
| Message      | Shown to the seller; may name the field and the actual value                                                                                    |
| Fix hint     | One sentence on how to fix it                                                                                                                   |

### 5.2 Loading and editing

- Rule files are validated against a schema at start-up; an invalid file stops start-up with a clear message.
- Administrator overrides in Settings use the same structure and can change severity, limits or messages, or disable a rule. Disabling is audited.
- Marketplace schemas and templates generate rules in the same internal structure, so all rules are evaluated by one engine.

## 6. AI prompt structure

### 6.1 Prompt parts

Each copy-generation prompt has five parts:

1. **Role and rules.** Who the writer is; that only supplied facts may be used; that output must follow the given structure exactly; and that unknown facts must be omitted, never guessed.
2. **Facts.** A list of fact entries, each with a short fact identifier, a label, a value and a unit. Only verified, manual or seller-supplied facts are included.
3. **Marketplace brief:**
   - the marketplace;
   - the limits from the live schema or template (title length, highlights length, bullet count and length, description length, keyword byte limit);
   - the style rules from SRS section 8.4;
   - the brand voice;
   - the banned terms.
4. **Output contract.** The exact fields to return. Each bullet and the description must list the fact identifiers they rely on.
5. **Correction note.** Present only on retries: the exact rule violations from the previous attempt.

### 6.2 Generation settings

- Low temperature (0.3).
- A response length large enough for all fields.
- One request per variant per marketplace.
- Each prompt template has a version number stored with every draft. Changing a template increments the version.

### 6.3 Other AI tasks

Mapping, category and flag suggestions use the same structure. Each returns a confidence between 0 and 1 and a one-sentence reason.

## 7. Default brand voice and banned terms

### 7.1 Brand voice

The default brand voice is clear, factual and friendly, with no exaggeration. It is used until the seller sets their own in Settings.

### 7.2 Default banned terms

Matched as whole words, without regard to case:

| Group        | Terms                                                                                                           |
| ------------ | --------------------------------------------------------------------------------------------------------------- |
| Superlatives | best, No.1, number one, top rated, best seller, bestseller, cheapest, lowest price                              |
| Promises     | guaranteed, 100% guarantee, money back, risk free                                                               |
| Commercial   | free delivery, free shipping, cash on delivery, COD, sale, discount, offer, limited time, buy now               |
| Medical      | cure, treats, heals, prevents disease, clinically proven (unless backed by an evidence document on the product) |

Other marketplace names are also banned in any marketplace's content: Amazon, Flipkart, Meesho, Myntra, Ajio, Nykaa, Snapdeal. A marketplace's own name is allowed only where that marketplace's template requires it.

The seller can edit the list in Settings. Edits are audited.

## 8. Visual design

### 8.1 Style and tools

| Item       | Choice                                                                                                                                 |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Style      | A clean, professional admin tool, desktop-first and usable down to tablet width. Information-dense tables, no decorative illustrations |
| Components | Tailwind CSS with the shadcn/ui component set, and lucide icons                                                                        |
| Typography | Inter (or the system sans-serif). 14-point base size in tables, 16-point in forms                                                      |

### 8.2 Layout

- A left sidebar with the main sections: Catalogue, Drafts, Amazon, Flipkart, Meesho, Status, Reports, Audit, Settings, Health.
- A top bar holding the mock or live banner and the jobs button.
- The jobs drawer opens from the right.

### 8.3 State colours

The same colours are used everywhere, with a legend on the Status screen:

| Colour    | States                                                            |
| --------- | ----------------------------------------------------------------- |
| Grey      | Not started                                                       |
| Blue      | Draft, Approved, Validated                                        |
| Amber     | Submitted, Exported, Uploaded awaiting QC, Uploaded awaiting live |
| Green     | Live                                                              |
| Red       | Needs fix                                                         |
| Purple    | Write blocked, API scope missing, Needs human login               |
| Dark grey | Stale, Inactive                                                   |

Colour is never the only signal: every state also shows its name.

### 8.4 Forms

- Labels sit above fields.
- Required markers and marketplace labels appear next to each field label.
- Validation messages appear under the field.
- Long forms use collapsible sections with completeness counts.

### 8.5 Feedback

- Notifications appear only after server confirmation.
- Destructive or risky actions (any live write, any Flipkart overwrite) use a confirmation dialog that states exactly what will change.

### 8.6 Accessibility

Every control has a label. All actions are reachable by keyboard. Text contrast meets WCAG AA.

## 9. Demo data

When demo seeding is on, ListingPilot loads synthetic data covering every state:

- at least 30 variants across five categories;
- a mix of complete and incomplete compliance;
- drafts in each state;
- mock marketplace listings.

Every demo record is labelled as demo. Demo data is never loaded into the production database.

## 10. Messages, times and limits

| Topic          | Rule                                                                                                                                     |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Error messages | Plain English. Each names what failed, why, and what to do next. Raw marketplace messages are shown underneath, in an expandable section |
| Times          | Stored in UTC. Shown in Indian Standard Time, in the format 29 Oct 2026, 4:30 pm                                                         |
| Grid page size | 50 rows by default; maximum 500                                                                                                          |
| Uploads        | Maximum file size 25 megabytes for spreadsheets and 15 megabytes per image                                                               |
| Exports        | Large exports run as jobs and become downloadable when finished                                                                          |

## 11. Amendments to other documents

| Document                 | Change                                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------------- |
| HUMAN_HANDOFF section A5 | Also add LIVE_TEST_SKUS (section 3 above)                                                         |
| TEST_PLAN section 6      | Cleanup in live tests follows section 3 above, not the shorter wording there                      |
| BUILD_PLAN               | The import column mapping (section 1) is part of task M1.3. The production import in M8.2 uses it |
| SRS section 4.1          | The HSN and GST table also records its source: seller-supplied, template or verified (section 2)  |

Change to CLAUDE.md

Replace section 2 of CLAUDE.md with this:

markdown

## 2. Read the documents in this order

| Order | Document              | What it gives you                                                                                 |
| ----- | --------------------- | ------------------------------------------------------------------------------------------------- |
| 1     | RUNBOOK.md            | How sessions start, resume and end; read at the start of every session                            |
| 2     | docs/PRD.md           | What the product is, who it is for, and why each feature exists                                   |
| 3     | docs/SRS.md           | Exactly how it must work: data model, rules, adapters, API, screens                               |
| 4     | docs/SPEC_ADDENDUM.md | Decisions that complete the SRS; wins over the SRS, TEST_PLAN and HUMAN_HANDOFF where they differ |
| 5     | docs/BUILD_PLAN.md    | Milestones, dated tasks, acceptance criteria, what to cut if late                                 |
| 6     | docs/TEST_PLAN.md     | How every task is proven, including GUI tests and live tests                                      |
| 7     | docs/HUMAN_HANDOFF.md | The few things you cannot do yourself; never block on them                                        |
