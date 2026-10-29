# ListingPilot — instructions for Claude Code

## Read first

- docs/MVP_PLAN.md — scope, schedule, definition of done (source of truth for what to build now)
- docs/HOW_IT_WORKS.md — what the code currently does
- docs/ListingPilot_PRD_SRS_v1.1.md — full spec (only consult relevant sections)

## Stack and commands

- Backend: FastAPI in backend/app; run: `.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000`
- Frontend: Next.js in frontend; run: `cd frontend; npm run dev`
- Tests: `.venv\Scripts\python.exe -m pytest backend/tests -q` (must pass before finishing any task)
- Seed: `.venv\Scripts\python.exe backend/app/seeds/seed_pilot_data.py`

## Non-negotiable rules

1. Never show success in the UI for an action that failed on the backend. No fake IDs (ASIN, FSN, MSH-...). Demo data only when DEMO_MODE is explicitly on.
2. No silent fallbacks (database, broker, AI provider) that change where data goes. Fail loudly with a clear message.
3. AI never invents product facts. Content must come from product attributes.
4. Marketplace dropdown values are written exactly as in the template (preserve typos). Never auto-pick a Brand.
5. Official templates in docs/meesho/templates and docs/flipkart/templates are read-only masters; always write into an in-memory copy.
6. Every new table/row carries workspace_id and user_id (single fixed defaults for now). Pass workspace context through services and Celery jobs.
7. Credentials are encrypted at rest and never returned unmasked to the frontend.
8. Do not build anything listed as out of scope in docs/MVP_PLAN.md. If a task seems to need it, stop and ask.
9. Do not refactor frontend/app/page.js beyond what the task requires.
10. Use Alembic migrations for schema changes once they exist; never rely on create_all for changes.

## Working style

- For each task: read relevant code, propose a short plan, wait for approval, then implement.
- Add or update tests for every behaviour change.
- Keep changes small and focused; one task per commit with a clear message.
- After each task, update docs/HOW_IT_WORKS.md sections affected and tick items in docs/MVP_PLAN.md if completed.
- Report at the end: what changed, files touched, tests run, anything left undone.
