# AGENTS.md — ListingPilot

Instructions for every coding agent working in this repository (Claude Code, Codex, Cursor, Gemini CLI, Copilot, Antigravity) and for the people reviewing their work. This file is the single source of project rules.

## 1. Precedence

When instructions disagree, the higher item wins:

1. The developer's direct instruction in the current session.
2. This file. `CLAUDE.md` imports it (`@AGENTS.md`) and adds only Claude Code-specific notes; it never restates or changes these rules.
3. `docs/MVP_PLAN.md` for what to build now: scope, schedule, priorities, out-of-scope list.
4. Skills in `.agents/skills/`. Skills decide **how** to work, never **what** to build. Where a skill conflicts with this file, follow this file; section 9 lists the known conflicts.
5. The agent's own defaults.

## 2. What ListingPilot is

A single-seller tool that takes products from a master catalogue to accepted bulk uploads on Meesho. Amazon and Flipkart are paused until the Meesho workflow works end to end.

Deadlines, the feature freeze and the priority order when behind are in `docs/MVP_PLAN.md`. Read them there rather than relying on a copy.

Read before starting a task:

- `docs/MVP_PLAN.md`: scope, schedule, definition of done (source of truth)
- `docs/HOW_IT_WORKS.md`: what the code does today
- `docs/ListingPilot_PRD_SRS_v1.1.md`: full spec; read only the relevant sections (Meesho: §3.3, §12.3, §13.3)

## 3. Stack and commands (Windows, Git Bash or PowerShell)

| What | Command |
| --- | --- |
| Backend (FastAPI) | `.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000` |
| Frontend (Next.js) | `cd frontend; pnpm dev` (port 3000). Install dependencies with **pnpm** only; the lockfile is `pnpm-lock.yaml` |
| Tests, full suite | `.venv\Scripts\python.exe -m pytest backend/tests -q` |
| Tests, targeted | `.venv\Scripts\python.exe -m pytest backend/tests/test_meesho_export.py -q` (or `-k <name>`) |
| Seed | `.venv\Scripts\python.exe backend/app/seeds/seed_pilot_data.py` |

- Always use `.venv\Scripts\python.exe`, never a bare `python` or `pip`.
- The local `.venv` runs Python 3.15.0. That is the current development interpreter, not a project requirement. The deployment version is not decided, so don't rely on syntax or standard-library features newer than Python 3.12, and check that a new dependency supports both versions.
- Backend: FastAPI, **synchronous** SQLAlchemy 2.0 + psycopg2, Pydantic v2, Celery + Redis, openpyxl.
- Database: Supabase PostgreSQL via `DATABASE_URL` (Session pooler on IPv4 networks). There is no local or SQLite database.
- Frontend: Next.js 16 (App Router, Turbopack), React 19, plain JavaScript. Every component is a client component calling the FastAPI backend at `NEXT_PUBLIC_API_BASE`. Next.js 16 differs from older versions: read `frontend/AGENTS.md` and the docs in `frontend/node_modules/next/dist/docs/` before using a Next.js API.
- AI: `backend/app/services/ai_service.py`, provider set by `AI_PROVIDER` (Groq, OpenRouter, Anthropic).
- Tests need `TEST_DATABASE_URL`, a **separate** database. Every run drops and recreates its tables.

## 4. Non-negotiable product rules

1. **Honest UI.** Never show success for an action that failed on the backend. No fake IDs (ASIN, FSN, MSH-…). Demo data only when `DEMO_MODE` is explicitly on. A successful Meesho export marks drafts "exported", never "live".
2. **No silent fallbacks** that change where data goes (database, broker, storage, AI provider). Fail loudly with a message the seller can act on.
3. **AI never invents product facts.** Copy comes only from product attributes.
4. **Marketplace values are written exactly as in the template**, typos included. Never auto-pick or snap a Brand. Only exact or high-confidence dropdown matches are written; low-confidence ones go to a review list.
5. **Official templates are read-only masters** (`docs/meesho/…`, `docs/flipkart/templates`). Always write into an in-memory copy. Never save over a master, including with spreadsheet tools.
6. **Every new table or row carries `workspace_id` and `user_id`** (single fixed defaults for now). Pass workspace context explicitly through services and Celery tasks.
7. **Credentials are encrypted at rest** and never returned unmasked to the frontend.
8. **Do not build anything on the out-of-scope list in `docs/MVP_PLAN.md`.** If a task seems to need it, stop and ask.
9. **Do not refactor `frontend/app/page.js`** beyond what the task requires.
10. **Schema changes go through Alembic migrations**, never `create_all`.

Meesho export gate (all-or-nothing): a file is produced only when every selected product passes every check in `docs/MVP_PLAN.md` ("Export gate"). Titles over 100 characters are **blocked, never truncated**.

## 5. Engineering standards

### 5.1 Backend

- Follow the existing layout: routers in `backend/app/api/v1/endpoints/`, business logic in `services/`, ORM models in `models/`, Pydantic schemas in `schemas/`, Celery jobs in `tasks/`. Do not add new layers (repositories, a DI framework, an async engine) without approval.
- Sessions come from `get_db` (sync). Celery tasks open their own `SessionLocal()` session and close it. Never share a session across threads or tasks.
- Use Pydantic v2 APIs only (`model_validate`, `model_dump`, `ConfigDict`).
- A failed operation returns a non-2xx status with a specific message the seller can act on. Never return 200 with an error inside the body, and never swallow an exception to keep a request "green".
- Configuration lives in `backend/app/core/config.py`. A new env var also goes in `.env.example` with a comment, and never with a real value.
- Match the surrounding code: its naming, comment density, and logging style (`print(..., flush=True)` with a component prefix).
- Keep marketplace rules in their adapters (`meesho_adapter.py`, `marketplace_limits.py`, `rule_engine.py`). Don't duplicate limits or word lists in other modules.

### 5.2 Database

- `DATABASE_URL` is the only application database; `TEST_DATABASE_URL` is the only test database. Never point a test, script, or seed at the production database by accident, and never run destructive SQL against `DATABASE_URL` without explicit approval.
- Schema changes: Alembic only. Do not use the Supabase CLI (`supabase db push/pull`, `apply_migration`) or the Supabase dashboard for schema changes. If Alembic is not set up yet and your task needs a schema change, raise it: setting up Alembic is its own task.
- Each migration: one logical change, reviewed by hand (autogenerate output is a draft), with a working `downgrade()`.
- New tables: `workspace_id` and `user_id` (non-null, indexed), indexes on foreign-key columns, `created_at` and `updated_at`. Use lowercase snake_case identifiers.
- Use bulk inserts and avoid N+1 queries in catalogue import and export paths.

### 5.3 Database access model and RLS

- **Access model (MVP):** only the FastAPI backend reads and writes the database, over `DATABASE_URL`, as the table owner. The browser, and Supabase's `anon` and `authenticated` roles, have no access to any table. `docs/HOW_IT_WORKS.md` records this model; update it in the same task if it ever changes.
- Tables in `public` are reachable through Supabase's Data API, so enable RLS on every new table in its migration **with no policies**. That denies the Data API roles everything. The backend is unaffected because RLS doesn't restrict the table owner unless `FORCE ROW LEVEL SECURITY` is set (don't set it).
- **Do not write `auth.uid()` or other per-user policies.** There is no authentication in the MVP, so such policies would protect nothing. Policies are designed together with auth, after the MVP.
- After applying a migration that adds a table, check the real exposure. A read-only request to `/rest/v1/<table>` with the project's anon key must return no rows or a permission error. Put the result in the task report.
- **Existing tables: exposure UNVERIFIED.** The tables created before Alembic (products, drafts and the rest) were made by `create_all` and probably have RLS off. Whether the anon key can read them through the Data API has **not been checked**. Treat them as possibly exposed, and don't describe them as protected in docs, reports or the UI until the read-only anon-key check is done and its result is recorded here. Running that check touches the live Supabase project, so do it only when the developer asks.

### 5.4 File and image storage

- Photos go to Supabase Storage **through the backend**. The service-role or secret key lives only in the backend environment, never in a `NEXT_PUBLIC_` variable or the browser.
- Validate uploads (PNG, JPEG or JPG only, size limit) before storing. Image ZIPs for Meesho are JPEG/RGB named `SKU_slot.jpg`.
- If storage is unreachable, fail the request. Never save to local disk as a fallback.

### 5.5 AI generation

- `ai_service.py` is the only module that calls an AI provider. The provider is chosen by configuration; never switch provider silently.
- Prompts are built only from the product's stored fields and attributes. Few-shot examples must not contain product facts (materials, sizes, claims) a model could copy into another product's listing; use structure-only examples.
- When no model produces a listing, the built-in template generator may write copy only if the result stays labelled (`engine` → `generation_source == "template"`) and the UI shows it as template copy. Never present template copy as AI copy.
- Limits come from `marketplace_limits.py`. Prompts ask for about 90 % of each limit; validation blocks anything over the limit and never truncates.
- Output is checked deterministically before a draft can be approved: length limits, Meesho-flagged words, no weight, dimension, price or portal names in the Product Name, no attribute that isn't in the product record.
- Tests never call a real provider. `conftest.py` blanks the API keys; provider tests set a fake key and mock `httpx` (see `test_ai_groq.py`).

### 5.6 Frontend

- New UI goes in `frontend/app/components/*.jsx`. `page.js` only wires new components in (rule 9).
- Every backend call has three visible states: loading, error (showing the backend's message), and success only on a 2xx response with real data. Use the backend's words for state: "Exported", "Not published", "Needs fixes". Never say "Live" or "Published" unless the marketplace confirmed it.
- Keep the visual language of the existing screens. No new UI kits, data-fetching libraries or other dependencies without approval.
- `NEXT_PUBLIC_*` values reach the browser. They must never hold secrets.

### 5.7 Security

- Never print, log, commit, or paste the contents of `.env`, API keys, or database URLs with passwords. Mask secrets in logs and API responses.
- Credentials are stored encrypted through `SettingsService` and returned masked.
- There is no auth in the MVP (out of scope). Keep CORS restricted to `BACKEND_CORS_ORIGINS`, and don't add endpoints that expose credentials or bulk data without need.
- Spreadsheets and ZIPs from users or Meesho are untrusted input: parse with openpyxl in read mode, validate columns, and never evaluate formulas or macros.

### 5.8 Testing

- Every behaviour change adds or updates a test; every bug fix starts with a test that reproduces it.
- **While iterating**, run the targeted tests for the code you're changing (a single file or `-k`).
- **Before a task is reported done or proposed for commit**, run the full suite once. Report the exact command and result, and name any failing test, even one you didn't cause.
- Changes that touch only documentation (no code, tests or configuration) need no test run; say so in the report.
- **Never run two test sessions at the same time** (parallel agents, two worktrees, a watcher plus a manual run). They share `TEST_DATABASE_URL` and drop each other's tables.
- Mocks are for external systems (AI providers, Supabase Storage, Meesho files). Test the project's own code for real.
- The frontend has no test runner. Verify UI changes in a running browser against the real backend (section 8) and include in the report what you clicked and saw.

### 5.9 Workflow, commits and reporting

- For each task: read the relevant code, propose a short plan, **wait for approval**, then implement.
- Keep changes small and focused, one task at a time.
- **Agents prepare changes and tests; commits need the developer's approval.** When a task is done, list the files and propose a commit message, then wait. One approved task = one commit, containing only that task's files.
- Approving a written plan may include approval to commit each plan task as it completes. That approval must be explicit, and it covers only that plan.
- Never stage or commit uncommitted work you didn't make. Never push, merge, rebase, amend, force, rewrite history, or delete branches without being asked.
- After each task, update the affected sections of `docs/HOW_IT_WORKS.md` and tick completed items in `docs/MVP_PLAN.md`.
- End with a report: what changed, files touched, tests run (command and result), the proposed commit, and anything left undone or decided on the developer's behalf.

## 6. Skills: where they live and how to use them

27 skills are installed in `.agents/skills/` and pinned in `skills-lock.json`. This is their only location. Claude Code discovers them there (confirmed 3 Nov 2026); `.agents/skills/` is also the shared location for other agents, but check each agent's own discovery before relying on it.

- `.agents/skills/` is the single skill directory. Do not create `.claude/skills/` or any other agent-specific skill folder, and do not copy, move or symlink skills. If an agent stops finding them, report it rather than duplicating them.
- Use a skill when its trigger in section 7 matches the task. Say so in one line ("Using systematic-debugging for the failing export test") and skip it quietly when it doesn't match.
- Superpowers skills refer to each other as `superpowers:<name>`. Here they are installed under the bare name (`brainstorming`, `writing-plans`, …).
- Skills that are installed but not for this project are listed in section 10.
- Do not install, update or remove skills, or edit `skills-lock.json`, without being asked.

## 7. Which skill, when

| Skill | Use it in ListingPilot when… |
| --- | --- |
| `brainstorming` | A request leaves real product decisions open (e.g. how processed-file errors map back to drafts). Skip it for tasks already specified in `MVP_PLAN.md`. |
| `writing-plans` | An approved feature needs more than about three commits (e.g. processed-file import + correction sheet). |
| `executing-plans` | Carrying out a written plan in this session. This is the default executor (see section 9 for commits). |
| `subagent-driven-development` | Only when the developer asks for per-task review by subagents. |
| `dispatching-parallel-agents` | Investigating several independent failures at once: read-only investigation, no concurrent test runs. |
| `using-git-worktrees` | Only when asked, and only from a clean, committed tree. |
| `finishing-a-development-branch` | Work on a feature branch is done and the suite is green. |
| `test-driven-development` | Any backend behaviour change or bug fix. |
| `systematic-debugging` | Any bug, failing test, or unexpected behaviour, before proposing a fix. |
| `verification-before-completion` | Before saying anything is done, fixed, or passing. |
| `requesting-code-review` | After a multi-commit feature or before merging a branch. |
| `receiving-code-review` | When review feedback arrives, from a person or a reviewer agent. |
| `python-backend-expert` | Pydantic v2 schemas and Alembic migrations. Ignore its async-session, repository and auth patterns (section 9). |
| `supabase` | Supabase Storage (photo intake), Data API exposure checks, connection or pooler errors. |
| `supabase-postgres-best-practices` | Any migration, new table, index, constraint, or slow query. |
| `security` | Repo-wide audit: once before the feature freeze (date in `MVP_PLAN.md`), and when dependencies change. |
| `prompt-engineering` | Changing prompts or output parsing in `ai_service.py`. |
| `llm-evaluation` | Checking a prompt or model change against fixed products (deterministic checks only for the MVP). |
| `frontend-design` | New screens or components: use its guidance on copy, empty states and error states; match the existing look. |
| `vercel-composition-patterns` | Designing a new component's props and state (e.g. picker, upload panel). |
| `vercel-react-best-practices` | Writing or reviewing client React code (re-render, effect and JS rules; ignore server-component rules). |
| `webapp-testing` | Scripted browser checks of real flows (needs Playwright; installing it requires approval). |

## 8. Skill combinations by task

| Task | Skills, in order |
| --- | --- |
| New Meesho backend feature (e.g. processed-file import) | `brainstorming` (short) → `writing-plans` → `executing-plans` + `test-driven-development` → `verification-before-completion` → `requesting-code-review` |
| Small backend change already specified in `MVP_PLAN.md` | Short plan in chat → `test-driven-development` → `verification-before-completion` |
| Schema change / new table | `supabase-postgres-best-practices` + `python-backend-expert` (Alembic part) → `test-driven-development` → Data API exposure check (5.3) → `verification-before-completion` |
| Photo intake / Supabase Storage | `supabase` + `security` (upload checks, key handling) → `test-driven-development` → `webapp-testing` → `verification-before-completion` |
| AI copy or prompt change | `prompt-engineering` → `llm-evaluation` (deterministic checks) + `test-driven-development` (mocked provider) → `verification-before-completion` |
| New frontend component | `frontend-design` (states and copy) + `vercel-composition-patterns` + `vercel-react-best-practices` → browser check → `verification-before-completion` |
| Bug or failing test | `systematic-debugging` → `test-driven-development` (reproducing test) → `verification-before-completion` |
| Several unrelated failures | `systematic-debugging` + `dispatching-parallel-agents` (investigate in parallel, fix and test one at a time) |
| Review feedback received | `receiving-code-review` → `test-driven-development` per fix → `verification-before-completion` |
| Before the feature freeze | `security` (full audit) → fix findings with `test-driven-development` → `finishing-a-development-branch` |

Browser checks: in Claude Code, use its browser tools (Claude in Chrome) against `http://localhost:3000` with the backend on port 8000. Other agents use `webapp-testing` once Playwright is installed. Always confirm that a failing backend call shows an error, not success.

## 9. Project overrides for installed skills

| Skill | What it says | What to do here |
| --- | --- | --- |
| `using-superpowers` | Invoke a skill if there is even a 1 % chance it applies, before any response. | Use the triggers in section 7. Don't load skills for questions, reading code, or one-line fixes. |
| `brainstorming` | Hard gate: design doc in `docs/superpowers/specs/`, committed, plus a subagent "builder check". | For MVP tasks, the approved short plan in chat is the design. Write a design doc only for multi-day features; committing it follows 5.9. |
| `writing-plans` | Commit after every TDD step; save to `docs/superpowers/plans/`. | Save plans there if a written plan is needed. At most one commit per plan task, and only with the approval described in 5.9. |
| `executing-plans`, `subagent-driven-development` | Commit each task and track progress by commit range; "continuous execution", no check-ins; never start on `main` without consent. | Use their ledger flow only when the plan's approval included per-task commits (5.9). Otherwise implement the plan task by task without their scripts and stop for commit approval at the end. Continuous execution starts only after the plan is approved. Ask once whether to work on `main`. |
| `using-git-worktrees` | Create a worktree and run `npm install` / `pip install`. | A worktree branches from `HEAD`, so uncommitted work is missing; only use one from a clean tree. Copy `.env` in yourself (it is git-ignored), install with `pnpm` and `.venv\Scripts\python.exe -m pip`, and never run tests in two trees at once. |
| `dispatching-parallel-agents` | Agents fix their own failures and run tests concurrently. | Parallel agents investigate and report; fixes and test runs happen one at a time. Never let two agents edit `page.js`. |
| `test-driven-development` | No mocks unless unavoidable; delete code written before its test; run the whole suite after each change. | Mocking AI providers and Storage counts as unavoidable. "Delete code" never applies to existing or uncommitted work you didn't write in this session. Targeted tests while iterating, full suite at task end (5.8). |
| `requesting-code-review` | A review is mandatory after every task. | Required after a multi-commit feature and before merge. Optional for single small tasks (Claude Code's `/code-review` is enough). |
| `finishing-a-development-branch` | Offer merge, PR or keep. | Present the options; never push or open a PR without an explicit choice. |
| `python-backend-expert` | Async sessions, repository layer, `app/routes/`, JWT auth, domain exception handlers. Runs as a forked subagent. | Keep sync SQLAlchemy, the existing `api/v1/endpoints` + `services` layout, and no auth (out of scope). Use it for Pydantic v2 and Alembic only. |
| `supabase` | Make schema changes with the Supabase CLI or MCP and generate migrations with `supabase db pull`; RLS policies on `auth.uid()`. | Alembic owns the schema (rule 10). RLS without policies, per 5.3. Use the skill for Storage, Data API exposure and connection errors. |
| `prompt-engineering` | Fall back to another completion on API errors; blocklist-based injection filtering; old model IDs; scaffold a `prompts/` package. | Any fallback stays labelled (5.5). Don't create a `prompts/` package or add dependencies (LangChain, tenacity, SDKs) without approval. Take model IDs from config, not from the skill. |
| `llm-evaluation` | 50–200 labelled examples, calibrated LLM judge, CI gate. | For the MVP, deterministic checks on the pilot products only. Evals that call real providers run outside `pytest`, by hand, and never in the test suite. |
| `frontend-design` | Take aesthetic risks; make a distinctive identity. | Match the existing app. New screens stay consistent with current ones; the copy and error-state guidance applies in full. |
| `vercel-react-best-practices` | Server components, server actions, SWR, `after()`. | Not applicable: the app is all client components calling FastAPI. Use the client, re-render and JS rules. Don't add SWR. |
| `security` | Wire a GitLeaks pre-commit hook; run gitleaks, pip-audit, pnpm audit. | Audit and report by default. Installing tools or adding hooks is a config change and needs approval. gitleaks and pip-audit are not installed. |

## 10. Installed skills not used for ListingPilot work

Don't trigger these unless the developer asks for them by name:

- `next-bundle-optimizer`: bundle-size performance is not an MVP goal, and its fix mode rewrites import boundaries.
- `next-dev-loop`: needs the `agent-browser` CLI (not installed) and refuses to run without it. Use the browser checks in section 8.
- `diagnosing-superpowers`: only for analysing a superpowers session that went wrong. It can draft GitHub issues, so never post one without explicit approval.
- `writing-skills`: only for writing or editing skills.

## 11. Done means

- The full suite passed at the end of the task (command and result shown), or the change is documentation-only and says so. New behaviour has tests.
- The UI shows real backend results for the changed flow, including the failure path.
- New tables passed the Data API exposure check (5.3).
- `docs/HOW_IT_WORKS.md` is updated and `docs/MVP_PLAN.md` is ticked where relevant.
- A proposed commit (files and message) is waiting for approval, and the final report lists changes, files, tests, and anything left undone.
