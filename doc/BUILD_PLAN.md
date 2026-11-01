# ListingPilot — Build Plan

Thursday 29 October 2026 to Friday 20 November 2026

A milestone is complete only when:

- the full green gate passes, including live tests where credentials exist;
- the progress log has an entry for every finished task.

## 1. Schedule

| Dates | Milestone | Outcome |
|---|---|---|
| Thu 29 – Fri 30 Oct | M0 Foundation and safety | The stack runs; the write guard exists; health is real; the browser test harness works |
| Sat 31 Oct – Mon 2 Nov | M1 Master catalogue | Families, variants, compliance, media, import and export work end to end |
| Tue 3 – Wed 4 Nov | M2 Category-agnostic attributes | Marketplace schemas and templates ingested; dynamic forms; mapping review; completeness meters |
| Thu 5 – Fri 6 Nov | M3 Rules, AI and review | Rule engine, AI drafts, approval gate, audit log |
| Sat 7 – Mon 9 Nov | M4 Amazon | Proven against the mock server, then live: preview, publish, poll, offer update |
| Tue 10 – Wed 11 Nov | M5 Meesho file pipeline | Correct template exports, the twenty Meesho rules, processed-file loop |
| Thu 12 – Fri 13 Nov | M6 Flipkart | Listing sync, API offer updates, template export |
| Fri 13 – Sun 15 Nov | M7 Meesho panel automation | Session management, template download, image upload and link capture, sheet upload, QC sync |
| Mon 16 – Tue 17 Nov | M8 Operations and live pilot run | Status hub, reports, audit screen, production import, live pilot run |
| Wed 18 Nov | M9 Hardening | Full regression, fixes, performance; feature freeze at end of day |
| Thu 19 – Fri 20 Nov | M10 Documentation and handoff | Final documents, evidence and verification |

## 2. Tasks and acceptance criteria

### M0 Foundation and safety (Thu 29 – Fri 30 Oct)

| Task | Work | Acceptance |
|---|---|---|
| M0.1 | Create the repository structure from the SRS; the service definitions for all components; the Makefile commands; the .env example; ignore rules for .env, secrets, pilot data and sensitive artifacts | All services start with one command |
| M0.2 | Configuration loading with fail-fast checks; the test-database guard; structured logging with secret redaction | The API refuses to start when the database is unreachable; tests refuse to run against the production database |
| M0.3 | First migration: workspace, user, setting, audit event, job, panel session; default workspace and user; context object; repository workspace filter | A test proves another workspace's rows are invisible |
| M0.4 | Shared password gate and login screen | Every API route and page requires a session |
| M0.5 | Health endpoint and Health screen with real checks (marketplace checks show "not configured" until their milestones); mock and live banners | Stopping the database shows it as down |
| M0.6 | The write guard and its status endpoint | A test covers every combination of mode, switch, allowlist, creator and action |
| M0.7 | Web shell: navigation, server-confirmed notifications, jobs drawer, generated typed API client | A notification never appears without a successful server response |
| M0.8 | Mock server skeleton; browser test harness with mock and live projects; continuous-integration workflow (mock only) | The smoke journey passes and saves screenshots |

Secret-redaction test: running sample flows leaves no secret value in logs or artifacts.

### M1 Master catalogue (Sat 31 Oct – Mon 2 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M1.1 | Models and migrations for brand, compliance party, product family, variant, attribute value, price offer and media tables; seed the core master attributes and a starter HSN and GST table, marked "to verify" in the handoff | Migrations apply cleanly on an empty database |
| M1.2 | Services and API with audit events; variant matrix from the variation theme; family-code and SKU uniqueness | Creating a size-and-colour family generates every combination with unique SKUs |
| M1.3 | Catalogue template; import with row-level errors and warnings, created and updated counts, update by SKU; export to Excel, CSV and JSON | Bad rows are reported by row number and field; an export can be re-imported unchanged |
| M1.4 | Media: upload, checks, renditions, duplicates; local and S3 storage; public addresses | Off-white and small images are flagged; with S3 configured, a live test confirms the public address works |
| M1.5 | Screens: setup wizard, catalogue grid, family page (core form, variants, media), import dialog with error list | Journeys J1 to J4 pass |
| M1.6 | Dry-run import of the pilot data into the development database, if present | Results recorded in the progress log |

### M2 Category-agnostic attributes (Tue 3 – Wed 4 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M2.1 | Reference tables from SRS section 4.1 | Migrations apply |
| M2.2 | Meesho template compiler; category tree loader; template upload in Settings | Every bundled template compiles; allowed values keep Meesho's exact spellings, including typos |
| M2.3 | Amazon schema ingestion and flattening, first against mock fixtures, then live for the pilot catalogue's product types (read-only) | Required, conditional, allowed-value and byte-limit details appear correctly; the live fetch is recorded |
| M2.4 | Flipkart template compiler with layout detection | A detectable fixture compiles; an undetectable one is marked as an unsupported layout without errors |
| M2.5 | Mapping engine and Mapping Review screen | Brand, colour, HSN, GST rate and country are never fuzzy-matched; unmapped fields are stored natively |
| M2.6 | Channel assignment with suggestion and confirmation; dynamic form; conditional fields; completeness meters | Journeys J5 and J6 pass |

### M3 Rules, AI and review (Thu 5 – Fri 6 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M3.1 | Rule engine with rule files, precedence, readiness and stale marking | A fact change marks dependent drafts stale |
| M3.2 | Product flags with toggles and AI suggestions | Toggling "imported" makes importer fields required |
| M3.3 | AI providers and the validation-and-retry loop | Titles over 75 characters and keywords over the byte limit are caught; ungrounded statements are rejected; a live test produces valid copy with the real key |
| M3.4 | Drafts: batch job with progress and cancel; editor with counters; approval gate; audit | Approval is refused with blocking issues; editing resets approval; journey J7 passes |

### M4 Amazon (Sat 7 – Mon 9 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M4.1 | Mock Amazon endpoints and scenarios from TEST_PLAN | Every scenario is reachable |
| M4.2 | Authentication and role probe | A missing role shows "API scope missing" with the role named |
| M4.3 | Existing-listing import through the Reports API | Imported listings are marked as not created by ListingPilot |
| M4.4 | Payload building, local validation, validation preview, catalogue match | Preview issues are shown against fields |
| M4.5 | Publish through the write guard; polling job; offer update; status mapping | No write happens without the guard; foreign listings are never modified |
| M4.6 | Amazon screen | Journey J8 passes |
| M4.7 | Live run: import existing listings; preview every pilot SKU; if allowlisted, publish one SKU, poll to ASIN or issues, then one offer update | Every step recorded in the live-run report; blocked steps recorded with reasons |

### M5 Meesho file pipeline (Tue 10 – Wed 11 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M5.1 | Identifier generation; filling into template copies; exact choice values | Golden-file test per bundled template: everything except data cells is identical, and data cells hold the expected values |
| M5.2 | Meesho rules MV-01 to MV-20 | Each rule has a passing and a failing test |
| M5.3 | Image package; link paste-back; link validation | Drive and WhatsApp links are rejected |
| M5.4 | Export package with checklist; refusal with a list of problems | Export is refused without Image 1 |
| M5.5 | Processed-file import; correction sheet | Errors map to fields; the correction sheet contains only failed rows |
| M5.6 | Meesho wizard in manual mode | Journey J9 passes |

### M6 Flipkart (Thu 12 – Fri 13 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M6.1 | Mock Flipkart endpoints, including paged listing search | Scenarios reachable |
| M6.2 | Authentication and scope probe | A missing scope is reported by name |
| M6.3 | Existing-listing sync through listing search, with report import as fallback | All pages fetched; FSNs stored |
| M6.4 | Template export from compiled verticals | Invalid rows held back with reasons |
| M6.5 | Offer and listing updates through the write guard, with difference confirmation | No update without confirmation; overwrite risk shown |
| M6.6 | Flipkart screen | Journey J10 passes |
| M6.7 | Live run: sync existing listings; if allowlisted, one price update that is verified and then restored | Recorded in the live-run report |

### M7 Meesho panel automation (Fri 13 – Sun 15 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M7.1 | Session manager (session-first, one scripted login per day at most); one-time login command; session check job; "needs human login" state and banner | An OTP prompt stops the worker and blocks panel jobs |
| M7.2 | Read-only discovery of the real panel; the panel map document; selectors with fallbacks; captured page fixtures with personal data removed | The panel map exists with screenshots |
| M7.3 | Template download job connected to the compiler | Live: one template downloaded and compiled |
| M7.4 | Image upload and link capture, guarded | Links mapped to SKUs by file name |
| M7.5 | Sheet upload, guarded; QC sync; error-file import | QC errors appear as "needs fix" |
| M7.6 | Wizard switches to automatic steps when automation is on and the session is valid, and to manual steps otherwise | Journey J11 passes, including an unexpected-page case |
| M7.7 | Live run: session check, template download, and, if allowlisted, image upload, sheet upload and QC sync | Recorded in the live-run report |

### M8 Operations and live pilot run (Mon 16 – Tue 17 Nov)

| Task | Work | Acceptance |
|---|---|---|
| M8.1 | Status grid, reports, audit screen, jobs drawer and settings completed | Reports match database counts; journeys J12 and J13 pass |
| M8.2 | Import the full pilot catalogue into the production database after a dry run on the test database | Import summary recorded; compliance gaps listed |
| M8.3 | Live pilot journey through the real interface against the real accounts: previews for all pilot SKUs; allowlisted SKUs taken to live on each marketplace | Live-run report updated with every identifier and state |

### M9 Hardening (Wed 18 Nov, feature freeze at end of day)

- Run every suite.
- Fix flaky tests.
- Check performance targets.
- Audit dependencies.
- Polish empty and error states.
- Check basic accessibility (labels, keyboard navigation, contrast).

### M10 Documentation and handoff (Thu 19 – Fri 20 Nov)

- Write HOW_IT_WORKS from the real code and the USER_GUIDE.
- Finalise the live-run report.
- Update the handoff, decisions and progress documents.
- Write a short demo script.
- Run the final full green gate and save its log in the artifacts folder.

## 3. Daily discipline

- Work only on tasks from the current milestone.
- End each day with all tests green and the progress log updated.
- If a task takes more than twice its expected time, reduce it to the minimum that meets its acceptance criteria, record the decision and move on.

## 4. If behind schedule, cut in this order

1. Flipkart template export (keep listing sync and offer updates)
2. Meesho panel sheet upload and QC sync (keep session, template download and image links)
3. Meesho panel automation entirely (the manual wizard remains complete)
4. Flipkart API offer updates
5. Jobs drawer polish and report charts

**Never cut:**

- the write guard;
- the honesty rules;
- Amazon preview and publish;
- the Meesho file pipeline;
- the tests.

## 5. Definition of done for Friday 20 November

- [ ] The full green gate passes; mock journeys J0 to J13 pass with screenshots saved
- [ ] Live tests have run for every marketplace with credentials; every skipped test states its reason
- [ ] No screen shows success for a failed or blocked action; no fake identifiers exist anywhere
- [ ] The write guard is enforced; nothing was deleted; no foreign listing was modified; no secret appears in logs or artifacts
- [ ] The pilot catalogue is in the production database, with compliance fields complete or listed as gaps
- [ ] Amazon: existing listings imported; every pilot SKU previewed; allowlisted SKUs live with real ASINs; one offer update verified
- [ ] Meesho: valid exports for every pilot category with a template; the processed-file loop works; panel automation works or is honestly blocked with the reason
- [ ] Flipkart: existing listings synced; template export works for available verticals; an allowlisted offer update is verified
- [ ] HOW_IT_WORKS, USER_GUIDE, LIVE_RUN_REPORT, HUMAN_HANDOFF, DECISIONS and PROGRESS are complete