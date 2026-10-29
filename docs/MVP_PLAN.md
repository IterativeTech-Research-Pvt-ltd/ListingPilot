# ListingPilot MVP Plan (deadline: Fri 20 Nov 2026)

## Goal

A single pilot seller takes real products to live listings on Amazon, accepted uploads on Meesho, and accepted uploads on Flipkart, and the UI never shows success for something that didn't happen.

## Source documents

- Spec: docs/ListingPilot_PRD_SRS_v1.1.md (single-seller MVP)
- Current state: docs/HOW_IT_WORKS.md (what the code does today)
- Meesho templates: docs/meesho/templates/\*.xlsx (read-only masters)
- Flipkart templates: docs/flipkart/templates/\*.xlsx (read-only masters, to be added)

## Spec conflicts in current code (fix first)

| Issue                                              | Fix                                                                                                                     |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Amazon title limit 200                             | 75 chars (all non-media since 27 Jul 2026); add Item Highlights field ≤125 chars to draft model, prompt, rules, payload |
| Amazon keywords "<250 bytes"                       | <200 bytes for Amazon.in, counted in UTF-8 bytes                                                                        |
| Meesho values silently snapped to dropdown options | Exact or high-confidence matches only; low-confidence snaps go to a review list; NEVER snap Brand                       |
| Meesho image cells use local/Unsplash URLs         | Image ZIP export + paste-back of Meesho panel-generated links; block export without Image 1                             |
| Style ID = SKU, Group ID empty                     | Style ID = family+colour once variants exist; Group ID per design family                                                |
| Meesho required fields from 6 hardcoded categories | Use the template's own "\* Compulsory Field" markers                                                                    |
| Silent SQLite fallback                             | Explicit DB via env; fail loudly if unreachable                                                                         |
| Dashboard fakes success on failure                 | Remove; demo data only behind explicit DEMO_MODE flag                                                                   |
| Fake ASIN/FSN/Meesho IDs                           | Remove; show honest "not published"/"exported" states                                                                   |

## In scope for 20 Nov

- Catalogue import with visible row errors; real pilot data
- AI copy for all 3 marketplaces with correct limits
- Rules, edit, approve, approval gate
- Amazon live: schema validation, validation preview, catalog search before create, publish, poll for real ASIN/issues, price/stock update
- Meesho: valid filled templates for all pilot categories, image-link flow, processed-file import
- Flipkart: template export for new products, FSN import from Seller Hub listings report, API price/stock for existing FSNs if access is granted
- Honest UI, real health checks, encrypted credentials, migrations with workspace_id/user_id

## Out of scope (do not build)

AI image generation, Shipping Optimiser, returns advisor, full Product Flags engine, template-compiler CI, audit log UI, Setup wizard, A+ publishing, auth/login, Celery progress bar, duplicate-image detection, Flipkart processed-file import, large refactors of page.js.

## Schedule

| Dates     | Work                                                                                                                                                        |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 28–31 Oct | Foundations: honest UI/reports/health; explicit DB; Alembic + workspace_id/user_id; encrypted credentials; remove fake IDs; Amazon limits + Item Highlights |
| 2–3 Nov   | Amazon schema validation + validation preview; Meesho image ZIP + link paste-back                                                                           |
| 4–5 Nov   | Amazon catalog search, publish, ASIN polling; Meesho validation, snapping review, IDs, name checks                                                          |
| 5–7 Nov   | Flipkart template parser                                                                                                                                    |
| 6 Nov     | Amazon price/stock; MILESTONE first real Meesho upload                                                                                                      |
| 9–11 Nov  | Flipkart template export; MILESTONE first Flipkart upload 11 Nov                                                                                            |
| 10 Nov    | MILESTONE Amazon go-live or validation-preview fallback decision                                                                                            |
| 12 Nov    | FSN import; Meesho processed-file import                                                                                                                    |
| 13 Nov    | Flipkart API price/stock (if access)                                                                                                                        |
| 12–14 Nov | Remaining 5 Meesho templates; real catalogue import; Legal Metrology fields required                                                                        |
| 16–17 Nov | End-to-end pilot run                                                                                                                                        |
| 18 Nov    | MILESTONE feature freeze                                                                                                                                    |
| 18–20 Nov | Fixes, docs, demo; MILESTONE MVP 20 Nov                                                                                                                     |

## Priority if behind

Honest UI > Amazon live > Meesho accepted > Flipkart template upload > Flipkart API.

## Definition of done

- [ ] No screen shows success for a failed action; no fake ASIN/FSN/Meesho IDs
- [ ] Real pilot catalogue in production DB with Legal Metrology fields complete
- [ ] Amazon: live listings with real ASINs pulled back; a price/stock update confirmed
- [ ] Meesho: all pilot categories uploaded and accepted (or rejections imported and fixed)
- [ ] Flipkart: all pilot verticals uploaded and through QC; real FSNs imported; API price/stock if access granted
- [ ] Current Amazon limits enforced; credentials encrypted; migrations with workspace_id/user_id; tests passing
