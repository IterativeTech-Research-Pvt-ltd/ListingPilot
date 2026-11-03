# ListingPilot MVP Plan (deadline: Fri 20 Nov 2026)

## Goal

**Meesho first (decided 3 Nov 2026).** A single pilot seller takes real products from the master catalogue to accepted uploads on Meesho, and the UI never shows success for something that didn't happen. Amazon and Flipkart are paused until the Meesho workflow works end to end (see "After Meesho").

## Source documents

- Spec: docs/ListingPilot_PRD_SRS_v1.1.md (single-seller MVP; Meesho: §3.3, §12.3, §13.3)
- Current state: docs/HOW_IT_WORKS.md (what the code does today)
- Meesho templates: docs/meesho/Meesho Templates/\<category path\>/\*.xlsx (read-only masters, all 3,787 categories)
- Meesho taxonomy: docs/meesho/categories/meeshoCategories.json (4 levels, same tree as the supplier panel)

## Spec conflicts in current code (fix first)

| Issue                                              | Fix                                                                                                                     |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Meesho values silently snapped to dropdown options | Exact or high-confidence matches only; low-confidence snaps go to a review list; NEVER snap Brand                       |
| Meesho image cells use local/Unsplash URLs         | Image ZIP export + paste-back of Meesho panel-generated links; block export without Image 1                             |
| Style ID = SKU, Group ID empty                     | Style ID = family+colour once variants exist; Group ID per design family                                                |
| Meesho required fields from 6 hardcoded categories | Use the template's own "\* Compulsory Field" markers (done 3 Nov: export and approval)                                |
| Meesho export ignores approval and truncates titles | Export only approved drafts; block (never cut) titles over 100 characters                                              |
| Silent SQLite fallback                             | Explicit DB via env; fail loudly if unreachable                                                                         |
| Dashboard fakes success on failure                 | Remove; demo data only behind explicit DEMO_MODE flag                                                                   |
| Fake ASIN/FSN/Meesho IDs                           | Remove; show honest "not published"/"exported" states                                                                   |

## The Meesho workflow (in scope for 20 Nov)

1. **Catalogue:** import with visible row errors; real pilot data; Legal Metrology fields and Seller Details complete.
2. **Meesho category:** the seller picks it in a 4-level picker like the supplier panel (with search), shown as `A > B > C > D`. Stored by Meesho's template id; a default per seller category, overridable per product. Name matching only suggests, never decides.
3. **Photos:** the seller adds real photos as a link or an uploaded PNG/JPEG/JPG file. Stored in free object storage (Supabase Storage proposed). Image 1 required; images 2–4 optional.
4. **Copy:** AI Meesho copy within limits (prompt asks for 90 % of each limit); edit; approve.
5. **Upload selection:** the seller adds or removes products from the current bulk upload; each shows ready / its problems.
6. **Export gate (all-or-nothing):** the file is produced only when every selected product passes: approved draft, title ≤ 100 characters, no Meesho-flagged words, no weight/dimension/price/portal names in Product Name, Meesho Price < MRP, Wrong/Defective price < Meesho Price, every compulsory field filled with exact template values, Image 1 a usable web link (Meesho's uploader or the seller's own storage; never Drive, stock or local).
7. **Images for Meesho:** ZIP of the photos as JPEG/RGB `SKU_slot.jpg`; the seller uploads it in the panel's image uploader and pastes the links back; links matched to SKUs.
8. **Delivery:** ZIP with one filled template per category plus an upload checklist (category path to pick per file, counts, reminder to return the processed file). Successful export marks drafts "exported", never "live".
9. **Feedback:** import Meesho's processed file (ERROR STATUS / ERROR MESSAGE per row), store the reason on each draft, produce a correction sheet with only the failed rows.
10. **Foundations kept:** honest UI, real health checks, encrypted credentials, migrations with workspace_id/user_id.

## Out of scope (do not build)

AI image generation, Shipping Optimiser, returns advisor, full Product Flags engine, template-compiler CI, audit log UI, Setup wizard, A+ publishing, auth/login, Celery progress bar, duplicate-image detection, Flipkart processed-file import, large refactors of page.js.

## After Meesho (paused, not before the Meesho workflow is done)

- Amazon: Item Highlights (≤125 chars; the 75-char title and 200-byte keyword limits are already done, 2 Nov), schema validation, validation preview, catalog search, publish, ASIN polling, price/stock update
- Flipkart: template parser and export, FSN import, API price/stock if access is granted
- Paid storage or image CDN, if the free tier runs out

## Schedule

| Dates     | Work                                                                                                                         |
| --------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 3 Nov     | **Done 3 Nov:** Meesho category picker (template id, breadcrumb, category defaults); storage decision (Supabase Storage)     |
| 4 Nov     | **Done 3 Nov:** upload selection, readiness per product, all-or-nothing export gate; Meesho copy from the template and data with a fact check and up to 2 regenerations; size/weight columns for any template; `Meesho <column>` values; drafts marked "exported" |
| 4–5 Nov   | Photo intake (link or file → storage), JPEG/RGB image ZIP, link paste-back, upload checklist                                 |
| 5 Nov     | Seller: Seller Details, real attributes and photos, Meesho categories; regenerate and approve Meesho drafts                  |
| 6 Nov     | MILESTONE first real Meesho upload (at least 5 products)                                                                     |
| 7–10 Nov  | Processed-file import + correction sheet (checked against the 6 Nov file); end-to-end test of every pilot template           |
| 9–13 Nov  | QC feedback (~3 days) and fixes; upload the remaining pilot categories                                                       |
| 16–17 Nov | End-to-end pilot run, all categories                                                                                         |
| 18 Nov    | MILESTONE feature freeze                                                                                                     |
| 18–20 Nov | Fixes, docs, demo; MILESTONE MVP 20 Nov                                                                                      |

## Priority if behind

Honest UI > Meesho accepted > everything else.

## Definition of done

- [ ] No screen shows success for a failed action; no fake ASIN/FSN/Meesho IDs
- [ ] Real pilot catalogue in production DB with Legal Metrology fields complete
- [ ] Meesho: every pilot category uploaded and accepted (or rejections imported and fixed)
- [ ] Meesho export refuses anything incomplete; processed-file errors come back to the drafts
- [ ] Credentials encrypted; migrations with workspace_id/user_id; tests passing
