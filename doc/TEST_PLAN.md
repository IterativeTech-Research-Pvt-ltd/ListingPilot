# ListingPilot — Test Plan

## 1. Test layers

| Layer | Tool | What it covers | Runs with |
|---|---|---|---|
| Unit | Pytest | Pure logic: rules, mappings, transforms, write guard, parsers, identifier generation | make test |
| Integration | Pytest with a containerised database and a temporary storage folder | Services and API routes against a real database | make test |
| Contract | Pytest against the mock marketplace server | Every adapter call, response handling, retries and error states | make test |
| Golden file | Pytest with Excel comparison | Meesho and Flipkart exports compared cell by cell and validation by validation with the originals | make test |
| Frontend | Vitest, TypeScript checking, ESLint | Components, hooks, the notification rule | make web-test |
| Browser (mock) | Playwright | Full user journeys on the full stack in mock mode with the fake AI provider | make e2e |
| Live | Pytest, live-marked | Real accounts: reads, previews and allowlisted writes | make live-test |
| Browser (live) | Playwright live project | The pilot journey through the real interface on the real accounts | make live-e2e |

## 2. Database safety

- The test database is recreated at the start of every test session.
- If the test database address equals the production address, or is empty, the run stops before anything else happens.

## 3. Fixtures

| Fixture | Contents |
|---|---|
| Synthetic catalogue | At least 40 variants across at least five categories, including imported, pre-packed, size-and-colour, missing-field and duplicate cases |
| Images | Pure white background (passes), off-white background (fails Amazon), small image (fails), duplicate pair, CMYK image |
| Meesho templates | Every bundled official template |
| Flipkart templates | Two synthetic vertical templates: one with a detectable layout, one deliberately undetectable |
| Amazon schemas | Fixtures for three product types following Amazon's documented format; replaced by recorded real schemas (secrets removed) after the live fetch in M2.3 |
| Meesho panel pages | Pages captured during discovery in M7.2, with personal data removed, served by the mock server |

## 4. Mock marketplace behaviour

The mock server is deterministic. The behaviour is chosen by words contained in the SKU.

| SKU contains | Amazon behaviour | Flipkart behaviour |
|---|---|---|
| Nothing special | Accepted; polling returns an ASIN with the MOCK- prefix, then a buyable status | Update succeeds |
| INVALID | Publish returns invalid with two field issues | Returns field errors |
| SLOW | ASIN appears only after three polls | Not applicable |
| LATEISSUE | Accepted, then an error-level issue appears while polling | Not applicable |
| RATE | First call returns a rate-limit response with a retry delay | First call returns a rate-limit response |
| NOROLE | Permission error naming a missing role | Permission error naming a missing scope |

The mock server also provides:

- Amazon: the token endpoint, product type search and definitions, schema files, catalogue search (one fixed GTIN matches an existing product), and the Reports API with an existing-listings report;
- Flipkart: the token endpoint, paged listing search, listing details, and listing create and update;
- Meesho: the captured panel pages.

## 5. Browser journeys in mock mode

Each journey saves screenshots in a folder named after the journey inside artifacts/e2e.

| Journey | Steps | Key assertions |
|---|---|---|
| J0 Smoke | Log in; open Health | Login works; real statuses shown; mock banner visible |
| J1 Setup | Complete profile, brand and compliance parties | Saved and shown; connection statuses displayed |
| J2 Create family | Create a size-and-colour family | All variants created with unique SKUs; audit entry exists |
| J3 Import and export | Import a file with errors; export; re-import | Errors listed by row and field; counts correct; round trip unchanged |
| J4 Media | Upload good and bad images | Checks shown; off-white flagged for Amazon; renditions listed |
| J5 Category and dynamic form | Assign marketplace categories; toggle a flag | Category fields appear with exact dropdown values; conditional field appears after the toggle; meters update |
| J6 Mapping review | Confirm a low-confidence mapping | Mapping saved and reused on the next product |
| J7 Drafts | Batch generate; edit; approve | Progress shown; a title over 75 characters is an error; approval refused, then allowed after the fix; editing resets approval |
| J8 Amazon | Preview an INVALID SKU, fix it, publish, wait, update the offer; try a NOROLE SKU | Issues shown against fields; status moves from submitted to live with a MOCK- ASIN; offer update confirmed; missing role shown honestly |
| J9 Meesho manual | Try to export without Image 1; download the image package; paste links; export; mark uploaded; import a processed file with errors | Export refused with a problem list; export succeeds after links; rows become "needs fix" with messages; correction sheet downloads |
| J10 Flipkart | Sync existing listings; export a template; try an unsupported template; update an offer | FSNs appear; unsupported layout shown honestly; difference confirmation required |
| J11 Meesho automatic | Run the automated wizard on captured pages; then hit an unexpected page | Images uploaded, links captured, sheet uploaded, QC synced; the unexpected page gives a blocked job with a screenshot and a manual fallback |
| J12 Status, reports, audit | Open each screen after the earlier journeys | Grid states match the database; report numbers equal database counts; audit lists the actions |
| J13 Honesty | Stop the mock server and publish; stop the API and save; switch to live mode with writes off and publish | Health shows down and no success notification appears; error notifications with no state change; "write blocked" shown with the would-be payload |

## 6. Live tests

Live tests run only when the matching credentials exist. Each skipped test states why.

| Test | Type |
|---|---|
| Amazon token and role check | Read |
| Amazon schema fetch for pilot product types | Read |
| Amazon existing-listing import | Read |
| Amazon validation preview for every pilot SKU | Preview (not a write) |
| Amazon publish of an allowlisted SKU, polling, offer update, stock set to zero if the SKU is marked test-only | Guarded write |
| Flipkart token and listing search | Read |
| Flipkart offer update on an allowlisted SKU, restored afterwards | Guarded write |
| Meesho session check and template download | Read |
| Meesho image and sheet upload for allowlisted SKUs, then QC sync | Guarded write |
| Public image address reachable from the internet | Read |
| AI produces valid copy with the real key | Read |

Each live test saves redacted evidence (request and response summaries, identifiers, screenshots) to artifacts/live and adds a line to the live-run report.

## 7. Safety and honesty tests

These must exist and must pass.

| Test | What it proves |
|---|---|
| Write guard matrix | Every combination of mode, switch, allowlist, creator and action gives the correct decision |
| No deletes | Adapters contain no delete calls, and a runtime check refuses any attempt |
| Secret scanning | After sample flows, logs and artifacts contain no value from .env |
| No fake identifiers | External identifiers are stored only from marketplace responses (or mock responses with the MOCK- prefix) |
| No success without confirmation | The frontend shows success notifications only after a successful server response |
| Foreign listings untouched | Listings not created by ListingPilot are never written unless allowlisted |

## 8. Continuous integration

- The workflow runs the full check and the mock browser journeys on every push.
- Live tests never run in continuous integration.
- Test reports and screenshots are kept as build artifacts.