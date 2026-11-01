# CLAUDE.md — Operating Instructions for Building ListingPilot

## 1. Purpose

You are building ListingPilot from an empty repository, working alone, from Thursday 29 October 2026 to Friday 20 November 2026.

Nobody will answer questions during the build. Your only inputs are:

- the documents in the docs folder,
- the .env file supplied by the owner,
- the data/pilot folder supplied by the owner (if present),
- the bundled marketplace templates in the docs folder.

Everything you need to decide is either written in these documents or covered by the autonomy rules below.

## 2. Read the documents in this order

| Order | Document              | What it gives you                                                   |
| ----- | --------------------- | ------------------------------------------------------------------- |
| 1     | docs/PRD.md           | What the product is, who it is for, and why each feature exists     |
| 2     | docs/SRS.md           | Exactly how it must work: data model, rules, adapters, API, screens |
| 3     | docs/BUILD_PLAN.md    | Milestones, dated tasks, acceptance criteria, what to cut if late   |
| 4     | docs/TEST_PLAN.md     | How every task is proven, including GUI tests and live tests        |
| 5     | docs/HUMAN_HANDOFF.md | The few things you cannot do yourself; never block on them          |

## 3. Inputs supplied by the owner

All inputs below are read-only. Never modify, move or commit them.

| Input                                                                                                                                                       | Location                                         | If it is missing                                                                                                                           |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Real credentials for one seller: Amazon SP-API, Flipkart self-access application, Meesho supplier login, Anthropic API key, S3 or R2 storage, Neon database | .env                                             | That channel or feature stays in mock mode. Its live tests are skipped with the reason "credentials missing". The handoff item stays open. |
| Live-write switch and SKU allowlist                                                                                                                         | .env (LIVE_WRITES_ENABLED and LIVE_WRITE_SKUS)   | No real writes happen. Every write path is still exercised up to the safety guard and reported as blocked.                                 |
| Pilot catalogue and photos                                                                                                                                  | data/pilot/catalogue.xlsx and data/pilot/photos  | Use the synthetic fixtures described in TEST_PLAN. Skip the production import.                                                             |
| Official Meesho category templates and category tree                                                                                                        | docs/meesho/templates and docs/meesho/categories | Download templates through the Meesho panel worker (milestone M7). Otherwise show the category as "template needed".                       |
| Flipkart vertical templates                                                                                                                                 | docs/flipkart/templates                          | Use synthetic fixtures for tests. Flipkart template export shows "template needed" for those verticals.                                    |

## 4. The real seller account is sacred

The credentials belong to a real business with real buyers. A mistake can change live prices, list wrong products or damage the seller's account health. These rules have no exceptions.

1. **Every marketplace write passes through the write guard** described in SRS section 10.1. A write is any of:
   - creating, updating or deleting a listing;
   - changing a price or stock level;
   - uploading a catalog file or images to a seller panel.
2. **A write is allowed only when all of these hold:**
   - the channel is in live mode;
   - live writes are switched on in .env;
   - the SKU is on the allowlist, or the allowlist is exactly an asterisk.
3. **Reads are always allowed.** Reads include:
   - fetching tokens and checking connection health;
   - downloading schemas, searching catalogues and reading listing status;
   - pulling reports, downloading templates and reading QC results.
4. **Amazon validation preview is not a write.** It checks a listing against Amazon's real rules without creating anything. Use it freely.
5. **Never delete a listing on any marketplace.** If a test listing must be withdrawn, set its stock to zero instead.
6. **Never modify a listing that ListingPilot did not create,** unless its SKU is explicitly on the allowlist.
7. **Respect rate limits.** For the Meesho panel, work at human pace: one action at a time, with pauses (SRS section 10.6).
8. **Never write a secret anywhere.** That covers logs, test output, screenshots, commit history and documents, and applies to passwords, tokens, cookies, API keys and session files. An automated test checks this.
9. **Tests never touch the production database.** The test database address must differ from the production one, or the test run stops immediately.

## 5. Autonomy rules

1. **Never stop to ask.** When something is unclear, choose the option that is simplest, honest, reversible and safe for the seller. Record the decision in docs/DECISIONS.md with:
   - a running number and the date;
   - the context;
   - the decision;
   - the alternatives considered;
   - how to reverse it.
2. **When something external fails,** do not stop. Examples: a login asks for an OTP, an API role is missing, a template is absent, a marketplace response is unexpected. In each case:
   - finish the code;
   - prove it against the mock marketplace server;
   - put the affected channel or feature into the honest blocked state the SRS defines (for example "needs human login" or "API scope missing");
   - add or update the item in docs/HUMAN_HANDOFF.md;
   - move on to the next task.
3. **When documents conflict,** the SRS beats the PRD, and the BUILD_PLAN beats both on scope and dates. Record the conflict in DECISIONS.
4. **When behind schedule,** cut scope only in the order given in BUILD_PLAN section 4. Never cut the safety rules, the honesty rules or the tests.
5. **Exploring the real Meesho panel** to learn its layout is allowed as read-only navigation with screenshots. Anything that would submit or upload obeys the write guard.

## 6. Honesty rules

Each rule below has an automated test that must pass.

- The interface never shows success for an action the backend did not complete.
- No fake marketplace identifiers (ASIN, FSN, listing ID, Meesho ID), statuses or report figures exist in any environment.
- **Mock mode:**
  - Every screen shows a persistent banner saying mock marketplaces are in use and nothing is sent to real accounts.
  - Every identifier returned by the mock server starts with the prefix MOCK-.
- **Live mode with writes switched on:** every screen shows a red banner with the number of SKUs that can be written.
- A write blocked by the guard is shown as "write blocked", with the reason and exactly what would have been sent. Never as success.
- Health checks genuinely connect to each dependency. Anything unreachable is shown as down.
- **No silent fallbacks:**
  - no switching to another database;
  - no swallowed errors;
  - no demo data unless the demo-seed setting is on.
- AI never invents facts. Any AI-suggested value below the confidence threshold blocks publishing until a person verifies it.

## 7. Working loop for every task

1. Read the task and its acceptance criteria in the BUILD_PLAN.
2. Write or extend tests first wherever practical, then implement.
3. Run the full check command (lint, type checks, backend and frontend tests). It must pass.
4. If the task touches the interface, run the browser test journeys affected by it. They must pass and save screenshots.
5. If the task touches a real integration and credentials exist, run the live tests for that channel.
6. Add one line to docs/PROGRESS.md: date, task number, status, evidence (test names, screenshot folders) and notes.
7. Commit with a message starting with the milestone and task number.
   - Never commit with failing tests.
   - Never commit .env, the secrets folder, the pilot data folder, or artifacts containing personal data.

## 8. Commands to create in milestone M0

Every command is a Makefile target run from the repository root.

| Command           | What it does                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| make up           | Starts all services: database, Redis, API, worker, panel worker, web app, mock marketplace server |
| make down         | Stops all services                                                                                |
| make migrate      | Applies all database migrations                                                                   |
| make seed         | Loads reference data; also loads synthetic demo data when demo seeding is on                      |
| make test         | Runs backend unit, integration, contract and golden-file tests (mock only)                        |
| make web-test     | Runs frontend unit tests, type checking and linting                                               |
| make e2e          | Runs all browser journeys against the full stack in mock mode                                     |
| make live-test    | Runs live-marked tests against the real accounts: reads, previews and allowlisted writes only     |
| make live-e2e     | Runs the browser pilot journey against the real accounts                                          |
| make meesho-login | Opens a visible browser so a person can log in to Meesho once; saves the session                  |
| make check        | Lint, type checks, backend tests and frontend tests together                                      |
| make all-green    | check plus e2e, plus live-test when credentials exist; the gate for every milestone               |

## 9. Engineering conventions

- **Backend:**
  - Python 3.12, FastAPI, SQLAlchemy 2 with typed models, Pydantic 2, Alembic migrations.
  - Celery with Redis for background jobs.
  - httpx for HTTP, openpyxl for Excel, Pillow for images, jsonschema for Amazon validation, Playwright for the Meesho panel worker.
  - Ruff for linting; mypy on services and adapters.
- **Frontend:**
  - Next.js with the App Router and TypeScript in strict mode.
  - TanStack Query for server state, TanStack Table for grids, React Hook Form with Zod for forms.
  - Playwright for browser tests.
- **Size and structure:**
  - No source file longer than 400 lines.
  - One folder per feature, in both backend and frontend.
- **Test IDs:** every interactive element carries a test identifier in the form page-element, so browser tests never depend on visual text.
- **Logging:** structured JSON through the standard logging system, with automatic secret redaction. No print statements.
- **Data access:** all through services that receive a context holding the workspace ID and user ID. Every background job carries the workspace ID.
- **Units:**
  - money as whole paise;
  - weights in grams;
  - lengths in millimetres;
  - conversion only at the edges (forms, exports, marketplace payloads).

## 10. Final deliverables (milestone M10)

| Deliverable             | Content                                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| docs/HOW_IT_WORKS.md    | A factual description of the code as built: every screen, action, job, adapter and state, with file references           |
| docs/USER_GUIDE.md      | A plain-language guide for the seller-operator                                                                           |
| docs/LIVE_RUN_REPORT.md | Everything really previewed, published, uploaded or changed on each marketplace, with identifiers, states and timestamps |
| docs/HUMAN_HANDOFF.md   | Updated, with every item marked done or open                                                                             |
| docs/DECISIONS.md       | All decisions taken during the build                                                                                     |
| docs/PROGRESS.md        | The full task log with evidence                                                                                          |
| artifacts/e2e           | Screenshots and reports for every mock journey                                                                           |
| artifacts/live          | Redacted evidence of every live test run                                                                                 |
