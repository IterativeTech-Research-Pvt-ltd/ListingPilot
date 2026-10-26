# ListingPilot PRD

Oct 13, 2026 · @Nishant

## 1. Overview

ListingPilot turns one master product sheet into complete, rule-checked listings on Amazon, Flipkart and Meesho, so the client enters each product once instead of three times. Nothing reaches a marketplace until it passes the checks and a person approves it.

| Item                | Detail                                                                                |
| ------------------- | ------------------------------------------------------------------------------------- |
| Product             | ListingPilot, marketplace listing automation                                          |
| Client              | \[Client name\], single client, one deployment                                        |
| Vendor              | IterativeTech, Jaipur                                                                 |
| Marketplaces        | Amazon (SP-API), Flipkart (Seller API), Meesho (bulk upload files)                    |
| Stack               | Python (FastAPI), PostgreSQL on Neon, Celery with Redis, Next.js, Claude API          |
| Duration            | 10 weeks, with a pilot sign-off at week 5 and go-live at week 10                      |
| Related document    | ListingPilot SRS (technical requirements)                                             |
| Purpose of this PRD | Define what is built, for whom, and how success is judged                             |
| After go-live       | IterativeTech has minimal interaction; the client uses and runs the system day to day |

## 2. Problem and background

Today the client's team types every product by hand into three seller portals. Each portal has different fields and rules, so one product is entered three times and mistakes are found only after a listing is rejected.

| Pain point                                               | Effect on the business                                         |
| -------------------------------------------------------- | -------------------------------------------------------------- |
| Same product entered three times                         | Repeated manual work per SKU, scaling with catalogue size      |
| Missing or wrong specs (size, material, category fields) | Rejected or hidden listings, lost sales days                   |
| Titles and bullets written by different people           | Uneven quality and weak search keywords                        |
| New products wait in a data-entry queue                  | Slow launches                                                  |
| No single view of status                                 | Nobody knows which products are live where, or which are stuck |

The pilot measures the current time per listing and the rejection rate, so every improvement claim is proven on the client's own numbers.

## 3. Goals and non-goals

**Goals**

1. One master catalogue is the single place products are entered and maintained.
2. Cut the time to create a listing and the first-pass rejection rate, against a measured baseline.
3. Catch missing specs and banned claims before submission, not after rejection.
4. Give listings consistent quality: brand voice, marketplace-specific length limits, relevant search keywords.
5. Give one live view of every SKU's status on every marketplace.
6. Protect the client's seller accounts: official APIs only, human approval before anything is published.
7. Keep the client in control: they own the data, accounts and credentials, and can export the full catalogue at any time.

**Non-goals**

- Ads management on Amazon, Flipkart or Meesho.
- WhatsApp integration (photo-to-listing, daily owner summary); can be added later as a separate project.
- Order processing, shipping labels and returns.
- Product photography, image editing and A+ content design.
- Marketplace fees, ad spend and Brand Registry costs.
- Automatic stock or order sync with Meesho.

## 4. Users

- **A single user** does everything: maintains the master catalogue, reviews, edits and approves drafts, fixes rejections, and uploads the Meesho files.
- One login; no separate roles or permissions.
- **IterativeTech:** builds, trains the user and supports the system.

## 5. Core user journey

&#91;embedded content: core user journey · sheet to listing, rejections loop back\]

The user fills the sheet once. Drafts must pass the checks and be approved by a person before Amazon and Flipkart receive them through their APIs or a Meesho file is prepared. A rejection returns with its reason, and the data is fixed and resent.

## 6. Scope

This covers the core listing tool only. Ads and WhatsApp can be added later as separate projects.

**Included**

| Area                | What is delivered                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| Master catalogue    | One Excel or Google Sheet template for all products; import from the existing sheet or a Tally export      |
| AI listing content  | Title, 5 bullet points, description and search keywords per product, adapted to each marketplace's limits  |
| Rule checks         | Required fields per category, title length, photo count and banned claims, checked before anything is sent |
| Review and approval | Web dashboard to review, edit and approve drafts; status of every SKU on every marketplace                 |
| Amazon              | Create and update listings, price and stock through the official SP-API                                    |
| Flipkart            | Create and update listings, price and stock through the Flipkart Seller API                                |
| Meesho              | Ready-to-upload bulk files in Meesho's category templates (Meesho does not offer a seller API)             |
| Error report        | Rejections from each marketplace shown with the reason, fixed and resent from one place                    |
| Training            | Two sessions for the user, plus a short user guide                                                         |
| Support             | Bug fixes, monitoring and marketplace rule updates for the support period                                  |

**Not included:** see section 3, non-goals.

**Phasing:** results are proven on the client's own pilot products on Amazon first, then extended to the other marketplaces.

## 7. Feature requirements

| #   | Feature                   | What it does                                                                                                                                                                    | Phase |
| --- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| F1  | Master catalogue          | One Excel or Google Sheet template for all products; import from the existing sheet or a Tally export                                                                           | 1     |
| F2  | AI listing content        | Title, 5 bullet points, description and search keywords per product, adapted to each marketplace's limits, in the brand voice                                                   | 2     |
| F3  | Rule checks               | Required fields per category, title length, photo count and banned claims, checked before anything is sent                                                                      | 2     |
| F4  | Review and approval       | Web dashboard to review, edit and approve drafts; status of every SKU on every marketplace                                                                                      | 2     |
| F5  | Amazon                    | Create and update listings, price and stock through the official SP-API                                                                                                         | 2     |
| F6  | Flipkart                  | Create and update listings, price and stock through the Flipkart Seller API                                                                                                     | 3     |
| F7  | Meesho                    | Ready-to-upload bulk files in Meesho's category templates; the user uploads them                                                                                                | 3     |
| F8  | Error report              | Rejections from each marketplace shown with the reason, fixed and resent from one place                                                                                         | 3     |
| F9  | Baseline and results      | Current time per listing and rejection rate measured in the pilot, then compared with pilot results                                                                             | 2     |
| F10 | Training and support      | Two training sessions and a short user guide; bug fixes, monitoring and marketplace rule updates for the support period                                                         | 4     |
| F11 | Self-serve administration | The client edits rule sets, banned claims, brand voice and Meesho templates, enters marketplace credentials, and sees failed jobs and expired credentials without IterativeTech | 4     |

**Rules that apply to every feature**

- Nothing goes to a marketplace until it passes the rule checks and the user approves it.
- Amazon and Flipkart listings are published through official seller APIs only; no bots or scraping.
- Meesho has no seller API, so ListingPilot fills Meesho's own upload templates and the user uploads them.
- Missing specs and banned claims are caught before submission, not after rejection.

**After go-live:** IterativeTech has minimal interaction once the site is deployed and used by the client. The system is therefore designed to run day to day without us: the client manages rules and templates (F11), and problems are shown and alerted to the client.

## 8. Dashboard

One web dashboard replaces the three separate data-entry jobs. It lets the user:

- review, edit and approve generated drafts;
- see the status of every SKU on every marketplace, including which products are live where and which are stuck;
- see rejections from each marketplace with the reason, and fix and resend from one place;
- see rule-check results before approving.

## 9. Success metrics

The pilot measures the current time per listing and the rejection rate, so the improvement is proven on the client's own numbers.

| Metric              | How it is measured                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| Time per listing    | Client's current figure (listings per month and time per listing) as baseline, compared with the pilot |
| Rejection rate      | Baseline vs pilot, from marketplace rejections recorded in the system                                  |
| Pilot SKUs live     | 50 to 100 pilot SKUs live on Amazon by pilot sign-off at week 5                                        |
| Checks and approval | Every published listing passed the rule checks and was approved by the user                            |

## 10. Release plan

&#91;embedded content: release plan · 4 phases over 10 weeks, 2 sign-offs\]

Amazon is proven on the pilot SKUs first and signed off at week 5. Flipkart and Meesho follow in weeks 6 to 8, and the full catalogue, training and support start in weeks 9 to 10. Timelines depend on marketplace access approvals and on receiving pilot data in week 1.

## 11. Dependencies and client inputs

Marketplace access takes longest to approve, so it starts in week 1 alongside the sample data.

| Area             | What the client provides                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| All marketplaces | Current product data for 50 to 100 pilot SKUs (Excel, Tally export or supplier catalogue); product photos, ideally 5 or more per product with one on a plain white background; size charts, materials and care details for each category; brand name, tone of voice, target keywords and claims to avoid; the person who will use ListingPilot; current listings per month and time per listing (baseline) |
| Amazon           | Professional selling account; primary account user registers as a private developer in Seller Central and requests the listing, pricing and inventory roles; Brand Registry and category approval status; list of existing ASINs                                                                                                                                                                           |
| Flipkart         | Registered Flipkart seller account; developer access created from Manage Profile, Developer Access (credentials stay on the client's side); existing listing IDs and brand approvals                                                                                                                                                                                                                       |
| Meesho           | Supplier panel access for the person who uploads files; latest category templates from the panel; existing Meesho SKU list                                                                                                                                                                                                                                                                                 |

**Client owns:** product data, marketplace accounts and API credentials throughout.

## 12. Assumptions and terms

- Single client, one deployment.
- Client data is not available yet; development starts with sample data until the client supplies the pilot data.
- The client owns product data, marketplace accounts and API credentials at all times. On exit, IterativeTech hands over the full master catalogue.
- Timelines depend on marketplace access approvals and on receiving pilot data in week 1.
- Marketplace fees, ad spend and Brand Registry costs are paid by the client directly to the marketplace.
- Marketplace rule or API changes are handled under the monthly support plan.
- AI drafts are reviewed and approved by the user before publishing; final listing content is the client's responsibility.
- New features beyond this scope, such as ads or WhatsApp, are quoted separately.
- Either party may end the monthly support with 30 days' notice after the minimum 6-month term.
- The proposal is valid for 30 days from its date.
