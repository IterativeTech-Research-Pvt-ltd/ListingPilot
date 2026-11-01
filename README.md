# ListingPilot

> **Marketplace Listing Automation for Amazon (SP-API), Flipkart (Seller API), and Meesho (Bulk Files)**
> Built by IterativeTech, Jaipur.

ListingPilot turns one master product sheet into complete, rule-checked listings on Amazon, Flipkart, and Meesho, replacing manual entry on each seller portal. Nothing reaches a marketplace until it passes the automated rule checks and a person approves it.

---

## Current Status: Production Ready — All Phases Complete

### What is Built and Working

#### Master Catalogue (CAT-1, CAT-2, CAT-3)

- **Template Generator**: Official multi-sheet Excel workbook with Forest Green styling, sample pilot SKUs, category-specific attribute requirements, and marketplace photography guidelines.
  `GET /api/v1/catalogue/template`
- **Import Engine**: Supports Excel (.xlsx), CSV (.csv), and Tally ERP XML exports. Smart fuzzy header matching, duplicate SKU detection, prohibited claims pre-check.
  `POST /api/v1/catalogue/import`
- **Export Engine**: Full catalogue export as Excel, CSV, or JSON with dynamic attribute columns.
  `GET /api/v1/catalogue/export?format=xlsx|csv|json`

#### Product Database and CRUD

- SQLAlchemy Product model on Supabase PostgreSQL: SKU, name, category, brand, MRP, price, stock, image URLs, dynamic JSON attributes.
- Full CRUD: `GET|POST /api/v1/catalogue/products`, `PUT|DELETE /api/v1/catalogue/products/{id}`
- Stats endpoint: `GET /api/v1/catalogue/stats`

#### AI Listing Generation (GEN-1 to GEN-4)

- OpenRouter API integration (free model: nvidia/nemotron-3.5-lightning:free) and Anthropic Claude.
- Generates title, 5 bullet points, description, and keywords per product per marketplace.
- Automatic heuristic fallback if API key is unavailable.
  `POST /api/v1/drafts/generate/{product_id}?marketplace=amazon|flipkart|meesho`
  `POST /api/v1/drafts/generate-batch?marketplace=amazon`

#### Compliance Rule Engine (RUL-1 to RUL-5)

- Prohibited claims check, title length limits per marketplace (Amazon 200 / Flipkart 150 / Meesho 95 chars).
- Minimum image count validation (3+) and white background requirement.
- Quality score (0-25) with per-issue severity and remediation hints.

#### Listing Draft Workflow (WF-1 to WF-3)

- 3-state lifecycle: draft -> approved -> live.
- Human approval gate: drafts with unresolved rule errors cannot be approved.
- Any edit re-runs the full rule engine automatically.

#### Marketplace Adapters

- **Amazon SP-API**: Stub mode (simulates ASIN). Live mode activated by AMAZON*SP_API*\* credentials in .env.
- **Flipkart Seller API**: Stub mode (simulates FSN). Live mode activated by FLIPKART_APP_ID / FLIPKART_APP_SECRET.
- **Meesho Bulk Export**: Fully functional. Generates .xlsx files ready for direct upload. No API key needed.

#### Reports and Baseline Metrics (RPT-1)

- Pipeline breakdown (draft / approved / live counts).
- Quality score distribution and first-pass approval rate.
  `GET /api/v1/reports/baseline`, `GET /api/v1/reports/draft-stats`

#### Settings and Administration (ADM-1 to ADM-3)

- Brand voice configuration, masked credential management, system health monitoring.
  `GET|PUT /api/v1/settings`

#### Next.js Web Dashboard

- Dark/light theme toggle, glassmorphism UI.
- Live KPI overview (Total SKUs, Available Stock, Average Price, Data Health Score).
- Drag-and-drop file import modal with real-time row-level validation feedback.
- Product Inspector drawer: dynamic attributes, photo gallery, marketplace pre-check status.
- AI Drafts and Review tab: generate, edit, approve, publish per marketplace.
- Multi-Channel Hub: Amazon / Flipkart / Meesho status matrix per SKU.
- Reports tab: quality scores, pipeline counts, ROI metrics.

#### Pilot Dataset

- 19 realistic artisan products from pilot brand Gulmohar Home, Jaipur.
- Categories: Bedsheets, Pooja items / Brassware, Kurtas, Planters, Ethnic Footwear, Quilts.

---

## Running Locally

### Prerequisites

- Python 3.11+ with uv (or pip)
- Node.js 18+ with npm
- Supabase project (DATABASE_URL and TEST_DATABASE_URL in .env; see .env.example)

### 1. Backend (FastAPI)

```powershell
# From project root D:\Education\Work\ListingPilot

# Seed the database with 19 pilot products
.venv\Scripts\python.exe backend/app/seeds/seed_pilot_data.py

# Start FastAPI dev server
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

- API Docs (Swagger): http://127.0.0.1:8000/api/v1/docs
- ReDoc: http://127.0.0.1:8000/api/v1/redoc
- Health check: http://127.0.0.1:8000/api/v1/health

### 2. Frontend (Next.js)

```powershell
cd frontend
npm install
npm run dev
```

### 3. Celery Background Worker (Optional / Production)

```powershell
# In production with Redis running:
.venv\Scripts\python.exe -m celery -A app.core.celery_app worker --loglevel=info -P solo
```

_(Note: If Redis is offline in local dev, ListingPilot automatically falls back to in-memory eager execution without crashing)._

### 4. Automated Tests

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -v
```

**32/32 tests passing** across all phases (catalogue, import/export, AI drafts, marketplace adapters, Celery & multi-tenant tasks, settings, health).

---

## Project Structure

```
ListingPilot/
├── backend/
│   └── app/
│       ├── core/               config.py, database.py, celery_app.py
│       ├── models/             SQLAlchemy ORM models (Product, ListingDraft)
│       ├── schemas/            Pydantic request/response DTOs
│       ├── tasks/              Celery background tasks (batch_tasks.py)
│       ├── services/
│       │   ├── rule_engine.py          Marketplace compliance checks
│       │   ├── template_generator.py   Excel template builder
│       │   ├── catalogue_parser.py     Excel / CSV / Tally XML ingestion
│       │   ├── catalogue_exporter.py   Excel / CSV / JSON export
│       │   ├── catalogue_service.py    Product CRUD and DB queries
│       │   ├── ai_service.py           OpenRouter / Claude generation
│       │   ├── amazon_adapter.py       Amazon SP-API (stub + live)
│       │   ├── flipkart_adapter.py     Flipkart Seller API (stub + live)
│       │   ├── meesho_adapter.py       Meesho bulk XLSX export (live)
│       │   └── settings_service.py     Brand voice and credentials
│       ├── api/v1/endpoints/
│       │   ├── catalogue.py, drafts.py, reports.py, settings.py, health.py
│       ├── seeds/seed_pilot_data.py    19 Gulmohar Home products
│       └── main.py                     FastAPI app, CORS, router wiring
├── frontend/
│   └── app/
│       ├── page.js         Full single-page Next.js dashboard
│       ├── layout.js       Root HTML shell and metadata
│       └── globals.css     Design system, dark/light themes
├── docs/
│   ├── PRD.md
│   └── SRS.md
├── .env                    All environment variables
├── pytest.ini
└── README.md
```

---

## Environment Variables

| Variable                    | Required | Description                                 |
| --------------------------- | -------- | ------------------------------------------- |
| DATABASE_URL                | YES      | Supabase PostgreSQL connection string       |
| OPENROUTER_API_KEY          | YES      | OpenRouter key (free tier works)            |
| OPENROUTER_MODEL            | no       | Default: nvidia/nemotron-3.5-lightning:free |
| ANTHROPIC_API_KEY           | no       | Optional direct Claude API key              |
| AMAZON_SELLER_ID            | no       | Activates live Amazon SP-API                |
| AMAZON_SP_API_CLIENT_ID     | no       | Amazon SP-API client ID                     |
| AMAZON_SP_API_CLIENT_SECRET | no       | Amazon SP-API client secret                 |
| AMAZON_SP_API_REFRESH_TOKEN | no       | Amazon LWA refresh token                    |
| AMAZON_AWS_ACCESS_KEY       | no       | AWS IAM access key                          |
| AMAZON_AWS_SECRET_KEY       | no       | AWS IAM secret key                          |
| AMAZON_AWS_ROLE_ARN         | no       | AWS IAM role ARN                            |
| FLIPKART_APP_ID             | no       | Activates live Flipkart API                 |
| FLIPKART_APP_SECRET         | no       | Flipkart app secret                         |
| NEXT_PUBLIC_API_BASE        | YES      | Frontend API base URL                       |

---

## API Reference

| Method | Endpoint                             | Description                                                |
| ------ | ------------------------------------ | ---------------------------------------------------------- |
| GET    | /api/v1/health                       | System health check                                        |
| GET    | /api/v1/catalogue/products           | List products                                              |
| POST   | /api/v1/catalogue/products           | Create product                                             |
| PUT    | /api/v1/catalogue/products/{id}      | Update product                                             |
| DELETE | /api/v1/catalogue/products/{id}      | Delete product                                             |
| GET    | /api/v1/catalogue/stats              | Catalogue health KPIs                                      |
| GET    | /api/v1/catalogue/template           | Download Excel template                                    |
| POST   | /api/v1/catalogue/import             | Import Excel / CSV / Tally XML                             |
| GET    | /api/v1/catalogue/export             | Export catalogue                                           |
| POST   | /api/v1/drafts/generate/{product_id} | Generate AI draft                                          |
| POST   | /api/v1/drafts/generate-batch        | Batch generate drafts (sync)                               |
| POST   | /api/v1/drafts/tasks/generate-batch  | Dispatch AI batch generation (Celery async / multi-tenant) |
| GET    | /api/v1/drafts/tasks/{task_id}       | Poll background task progress & status                     |
| POST   | /api/v1/drafts/tasks/publish-batch   | Dispatch batch publish task (Celery async)                 |
| GET    | /api/v1/drafts                       | List drafts                                                |
| PUT    | /api/v1/drafts/{id}                  | Edit draft (re-runs rules)                                 |
| POST   | /api/v1/drafts/{id}/approve          | Approve draft                                              |
| POST   | /api/v1/drafts/{id}/reject           | Reject draft                                               |
| POST   | /api/v1/drafts/{id}/publish          | Push to marketplace                                        |
| GET    | /api/v1/drafts/marketplace-status    | SKU x marketplace matrix                                   |
| GET    | /api/v1/reports/baseline             | Baseline metrics                                           |
| GET    | /api/v1/reports/draft-stats          | Draft quality stats                                        |
| GET    | /api/v1/settings                     | Get settings                                               |
| PUT    | /api/v1/settings/brand-voice         | Update brand voice                                         |
| PUT    | /api/v1/settings/credentials         | Update API credentials                                     |

Full interactive docs at http://127.0.0.1:8000/api/v1/docs

<!-- .venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000 -->
 