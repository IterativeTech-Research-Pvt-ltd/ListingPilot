# ListingPilot SRS

Oct 13, 2026 · @Nishant

## 1. Introduction

This SRS states what the ListingPilot system must do and the limits it must work within. Developers build from it and testers verify against it. Product intent and priorities are in the ListingPilot PRD.

**Scope:** a single-client web system that imports a master catalogue, generates marketplace-specific listing content with AI, checks it against rules, routes it through human approval, and publishes to Amazon and Flipkart through official APIs and to Meesho through generated upload files.

| Term             | Meaning                                                      |
| ---------------- | ------------------------------------------------------------ |
| SKU              | Stock keeping unit, one sellable product or variant          |
| Master catalogue | The single source of product data entered by the client      |
| Draft            | Generated listing content for one product on one marketplace |
| Rule set         | Configured checks for one marketplace and category           |
| Adapter          | Component that talks to one marketplace                      |
| SP-API           | Amazon Selling Partner API                                   |
| User             | The one person who uses ListingPilot and does everything     |
| Listing          | A draft published, or prepared for upload, on a marketplace  |

Requirement keyword: **shall** means mandatory.

## 2. Overall description

**Product perspective.** ListingPilot sits between the client's product data and three marketplaces. It does not replace any marketplace portal. It reads product data, writes listings through official channels, and keeps its own record of drafts, approvals and results.

**Users**

- **A single user** does everything: maintains the master catalogue, reviews, edits and approves drafts, fixes rejections, and uploads the Meesho files.
- One login; no separate roles or permissions.

**Operating environment (confirmed stack)**

- Backend: Python with FastAPI, PostgreSQL hosted on Neon, Celery workers with Redis.
- Frontend: Next.js web application.
- AI: Claude API.
- Single client, one deployment.

**Constraints**

- Official marketplace APIs only (Amazon SP-API, Flipkart Seller API); no bots or scraping.
- Meesho has no seller API, so Meesho output is the client's upload template filled in, uploaded by the user.
- Nothing goes to a marketplace until it passes the rule checks and the user approves it.
- The client owns product data, marketplace accounts and API credentials; Flipkart credentials stay on the client's side.
- Client data is not available yet; development starts with sample data.

**Dependencies**

- Marketplace access approvals take the longest and start in week 1.
- Pilot data of 50 to 100 SKUs is needed in week 1.

## 3. System architecture

&#91;embedded content: system architecture · dashboard, API, workers, marketplaces\]

The dashboard talks only to the API. The API stores state in PostgreSQL and queues work in Redis; workers import data, call the AI service, run the rule engine and publish through one adapter per marketplace. Meesho has no API, so its adapter writes a file that a person uploads.

## 4. Functional requirements

### 4.1 Catalogue (CAT)

| ID    | Requirement                                                                                      |
| ----- | ------------------------------------------------------------------------------------------------ |
| CAT-1 | The system shall provide one master catalogue template (Excel or Google Sheet) for all products. |
| CAT-2 | The system shall import products from the client's existing sheet or a Tally export.             |
| CAT-3 | The system shall let the client export the full master catalogue at any time, including on exit. |

### 4.2 AI listing content (GEN)

| ID    | Requirement                                                                                                                      |
| ----- | -------------------------------------------------------------------------------------------------------------------------------- |
| GEN-1 | The system shall generate, per product, a title, 5 bullet points, a description and search keywords.                             |
| GEN-2 | The system shall adapt the content to each marketplace's limits.                                                                 |
| GEN-3 | The system shall write in the client's brand voice using the client's target keywords and avoiding the client's claims to avoid. |
| GEN-4 | The system shall use only the product data supplied in the master catalogue.                                                     |

### 4.3 Rule checks (RUL)

| ID    | Requirement                                                                                                                                                                                 |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RUL-1 | The system shall check required fields per category.                                                                                                                                        |
| RUL-2 | The system shall check title length.                                                                                                                                                        |
| RUL-3 | The system shall check the photo count against the minimum set for the marketplace and category. The client supplies ideally 5 or more photos per product, one on a plain white background. |
| RUL-4 | The system shall check for banned claims.                                                                                                                                                   |
| RUL-5 | The system shall run the checks before anything is sent to a marketplace and report each failure so it can be fixed before submission.                                                      |

### 4.4 Review and approval (WF)

| ID   | Requirement                                                                                                                         |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------- |
| WF-1 | The system shall provide a web dashboard to review, edit and approve drafts.                                                        |
| WF-2 | The system shall send nothing to a marketplace until the draft passes the rule checks and the user approves it.                     |
| WF-3 | The dashboard shall show the status of every SKU on every marketplace, including which products are live where and which are stuck. |

### 4.5 Errors and baseline (ERR, RPT)

| ID    | Requirement                                                                                                                 |
| ----- | --------------------------------------------------------------------------------------------------------------------------- |
| ERR-1 | The system shall show rejections from each marketplace with the reason.                                                     |
| ERR-2 | The system shall let the user fix a rejected listing and resend it from one place.                                          |
| RPT-1 | The system shall support measuring current time per listing and rejection rate in the pilot, to compare with pilot results. |

### 4.6 Administration (ADM)

IterativeTech has minimal interaction after deployment, so the client runs the system day to day.

| ID    | Requirement                                                                                                                                                   |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ADM-1 | The system shall let the client edit rule sets, banned claims and brand voice without a code change.                                                          |
| ADM-2 | The system shall let the client upload and update Meesho category templates.                                                                                  |
| ADM-3 | The system shall let the client enter and update marketplace credentials, and show whether each one is present and working without displaying it.             |
| ADM-4 | The system shall alert the client by email and on the dashboard about failed jobs and expired credentials, and show the last successful sync per marketplace. |

## 5. Draft workflow

&#91;embedded content: draft workflow · 5 states and their transitions\]

Only an approved draft can be sent. Any edit returns the draft to Draft and re-runs the checks (WF-2). A rejection returns with its reason and is fixed and resent (ERR-1, ERR-2).

## 6. Rule checks and AI content

### 6.1 Rule checks

Before anything is sent, each draft is checked for: required fields per category, title length, photo count and banned claims. Rules differ per marketplace and category, including the photo minimum, and are held as configuration. When a marketplace changes its rules or API, the update is handled under the monthly support plan.

### 6.2 AI content

- **Input:** product data from the master catalogue, the marketplace's limits, the client's brand voice, target keywords and claims to avoid.
- **Output:** title, 5 bullet points, description and search keywords for each marketplace.
- **Approval:** AI drafts are reviewed and approved by the user before publishing; final listing content is the client's responsibility.
- **Service:** Claude API.

## 7. Marketplace integration

Official channels only. The system does not use bots or scraping.

| ID    | Requirement                                                                                                    |
| ----- | -------------------------------------------------------------------------------------------------------------- |
| AMZ-1 | The system shall create and update listings on Amazon through the official SP-API.                             |
| AMZ-2 | The system shall update price and stock on Amazon through the SP-API.                                          |
| FK-1  | The system shall create and update listings on Flipkart through the Flipkart Seller API.                       |
| FK-2  | The system shall update price and stock on Flipkart through the Flipkart Seller API.                           |
| MSH-1 | The system shall fill Meesho's category templates with approved listing content as ready-to-upload bulk files. |
| MSH-2 | The system shall not sync stock or orders with Meesho.                                                         |

**Access supplied by the client**

- **Amazon:** professional selling account; the primary account user registers as a private developer in Seller Central and requests the listing, pricing and inventory roles.
- **Flipkart:** registered seller account; developer access created from Manage Profile, Developer Access; credentials stay on the client's side.
- **Meesho:** supplier panel access for the person who uploads files, and the latest category templates.

Endpoint details are checked against each marketplace's current documentation during the build.

## 8. Data requirements

| Entity      | Holds                                                                                                                             |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Product     | Master catalogue record: SKU, name, category, brand, attributes such as size, material and care, price, stock, photos             |
| Draft       | Generated content per product and marketplace (title, bullets, description, keywords), its state, rule-check results and approval |
| Listing     | The published or prepared listing per product and marketplace, with its status                                                    |
| Rejection   | A marketplace rejection with its reason                                                                                           |
| Rule set    | Required fields, limits and banned claims per marketplace and category                                                            |
| Meesho file | Upload file generated per Meesho category                                                                                         |
| Credential  | The client's marketplace API credentials                                                                                          |

**Data rules**

- The client owns the data, accounts and credentials at all times.
- The full master catalogue is handed over to the client on exit.

## 9. External interface and UI

**User interface:** a web dashboard to review, edit and approve drafts, and to see the status of every SKU on every marketplace, plus rejections with their reasons.

| Interface                         | Direction  | Notes                                        |
| --------------------------------- | ---------- | -------------------------------------------- |
| Amazon SP-API                     | Out and in | Official, using the client's credentials     |
| Flipkart Seller API               | Out and in | Official, using the client's credentials     |
| Meesho supplier panel             | Manual     | System produces files; the user uploads them |
| Claude API                        | Out        | Generates listing content                    |
| Excel, Google Sheet, Tally export | In         | Master catalogue and import                  |

## 10. Non-functional requirements

| Area           | Requirement                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Compliance     | Official marketplace APIs only; no bots or scraping                                                                      |
| Safety         | Rule checks and user approval before every submission, so seller accounts stay protected                                 |
| Data ownership | The client owns product data, marketplace accounts and API credentials; the full master catalogue is handed over on exit |
| Credentials    | Flipkart credentials stay on the client's side and are never shared outside the client's account                         |
| Supportability | Marketplace rule and API changes are handled under the monthly support plan                                              |

**Low-maintenance operation:** IterativeTech has minimal interaction after the site is deployed and used by the client. The system must therefore run without our involvement: rules, templates and credentials are managed by the client (ADM-1 to ADM-3), and problems are visible and alerted to the client (ADM-4).

## 11. Delivery, training and support

**Delivery:** four phases over 10 weeks with two sign-offs: setup (weeks 1 to 2), Amazon pilot (weeks 3 to 5, pilot sign-off), Flipkart and Meesho (weeks 6 to 8), rollout (weeks 9 to 10, go-live and handover).

**Training:** two sessions for the user, plus a short user guide.

**Support:** bug fixes, monitoring and marketplace rule updates for the support period. Minimum term 6 months; either party may end the monthly support with 30 days' notice after that.

**Pilot acceptance:** the client signs off the pilot of 50 to 100 SKUs at week 5, with results compared to the baseline.

## 12. Acceptance criteria and traceability

**Acceptance criteria**

1. Pilot products (50 to 100 SKUs) are imported from the client's data (CAT-2).
2. Each draft has a title, 5 bullet points, a description and search keywords (GEN-1).
3. Missing fields, title length, photo count and banned claims are caught before submission (RUL-1 to RUL-5).
4. Nothing is sent to a marketplace without passing the checks and user approval (WF-2).
5. Approved pilot SKUs are live on Amazon with the approved content, price and stock (AMZ-1, AMZ-2).
6. Flipkart listings publish through the API and Meesho files are ready to upload (FK-1, FK-2, MSH-1).
7. A rejection shows its reason and can be fixed and resent from one place (ERR-1, ERR-2).
8. Results vs baseline are available at pilot sign-off (RPT-1).

**Traceability to PRD features**

| PRD feature                   | SRS requirements |
| ----------------------------- | ---------------- |
| F1 Master catalogue           | CAT-1 to CAT-3   |
| F2 AI listing content         | GEN-1 to GEN-4   |
| F3 Rule checks                | RUL-1 to RUL-5   |
| F4 Review and approval        | WF-1 to WF-3     |
| F5 Amazon                     | AMZ-1, AMZ-2     |
| F6 Flipkart                   | FK-1, FK-2       |
| F7 Meesho                     | MSH-1, MSH-2     |
| F8 Error report               | ERR-1, ERR-2     |
| F9 Baseline and results       | RPT-1            |
| F10 Training and support      | Section 11       |
| F11 Self-serve administration | ADM-1 to ADM-4   |
