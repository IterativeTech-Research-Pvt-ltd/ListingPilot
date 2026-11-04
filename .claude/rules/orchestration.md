# Task routing

The developer describes outcomes. Choose the workflow yourself and never ask which skill, test or agent to use. AGENTS.md sections 7–9 say which skill fits a task; this file adds triage, delegation and review. AGENTS.md wins any conflict. The developer has authorized specialist subagents for the cases below. Use the smallest set of tools that does the job.

## 1. Triage first

Check scope before loading any skill. If the request is on the out-of-scope list in `docs/MVP_PLAN.md`, or plainly needs something section 2 says to stop for, stop and ask now; don't load `brainstorming` or any other skill first, whatever its description says.

Otherwise pick the lowest tier that fits and name it in one line. Raise the tier if the work turns out bigger.

| Tier | Looks like | Plan | Review after |
| --- | --- | --- | --- |
| 0 | Question, typo, docs-only edit, reading code | None | None |
| 1 | Small bug or behaviour change in one area | None | `/code-review low` |
| 2 | Multi-file fix or small addition to something that already exists | Short plan in chat, then continue | `verifier`, `/code-review`, `ponytail:ponytail-review` |
| 3 | A new feature or workflow; schema, export gate, credentials, storage or AI prompts; or more than about 3 commits | Plan, then **wait for approval** | Tier 2 plus `security-reviewer` and `code-quality-reviewer`; `architect` before implementing |

A new feature means new endpoints, screens, file formats or status changes, even if each piece looks small. **When unsure between tier 2 and tier 3, choose tier 3**, and state the plan before writing any code.

## 2. Stay inside the outcome

Tiers 0–2 run without routine approval, but only within what the developer asked for. Stop and ask when any of these comes up:

- A significant product decision that `docs/MVP_PLAN.md` doesn't settle.
- Scope beyond the requested outcome, or anything on the out-of-scope list.
- A destructive operation, or deleting substantial existing functionality.
- A new dependency or tool, a schema change, production access, or a change to secrets or environment configuration.
- Any git write. Never stage, commit, push, merge or rewrite history unasked, and never touch uncommitted work you didn't make.

The local app runs on the real database. Subagents can only look at it: a hook refuses their clicks, typing and uploads, and limits their navigation to the frontend. On the main thread that limit is this rule alone, so ask the developer before any click that saves, uploads, generates, approves or exports, or before starting the backend. `GET /meesho/export` writes too: it marks drafts exported.

## 3. Skills the Skill tool refuses

Thermos and most pstack skills set `disable-model-invocation`. Reach them by reading `.agents/skills/<name>/SKILL.md` and following it, which is the route pstack documents. Only do this for:

| When | Read |
| --- | --- |
| Unfamiliar code before tier 2 or 3 work | `how` |
| A change to shared code (services, adapters, `rule_engine`) | `blast-radius` |
| Why code is the way it is | `why` |
| A tier 3 design with real alternatives | `architect` |
| A contested design | `interrogate` |
| Reporting a performance number you measured | `benchmark-checklist` |
| Writing docs or reports | `technical-writing`, `unslop` |

Their subagent settings are in `.claude/rules/pstack-models.md`. Cursor terms map through the pstack plugin's `docs/harness/claude-code.md`; when a step needs a Cursor-only feature, skip it and say so.

Never start these yourself; they run only when the developer types them: `poteto-mode`, `swarm`, `arena`, `automate-me`, `reflect`, `ketchup`, `ketchup-video`, `make-bot-ui`, `teach`. Don't apply `principle-never-block-on-the-human`. If any skill says to proceed past approval, commit, push, open a PR, or message an external service, AGENTS.md wins and that step is skipped.

Ponytail runs in `full` mode for the main thread and the implementers. Its "smallest complete change" applies, except that its exemption for trivial changes doesn't replace AGENTS.md 5.8: behaviour changes always get tests.

## 4. Delegation

Delegate when work is independent, spans backend and frontend, or needs an independent view. Do small work in the main thread.

| Agent | Use for | Access |
| --- | --- | --- |
| `backend-engineer` | FastAPI, services, Celery, tests | Writes; targeted tests |
| `frontend-engineer` | `frontend/app/components` | Writes |
| `database-supabase` | Draft migrations, Storage, RLS questions | Writes drafts; can't apply |
| `verifier` | Full suite and read-only browser checks at tier 2 and above | Can't edit code or act in the browser |
| `architect` | Design and blast-radius review | Read-only |
| `security-reviewer` | Security review of a change | Read-only |
| `code-quality-reviewer` | Thermos and Ponytail maintainability review | Read-only |

- Investigate in parallel; coordinate edits. One writer per file at a time, and only one agent may edit `frontend/app/page.js`.
- Don't use worktrees for agents: they branch from HEAD and miss uncommitted work.
- Only the main thread, `verifier` and `backend-engineer` run pytest, one session at a time. The guard hook enforces this.
- Subagents can't get approval. The guard refuses anything that needs it, so they report back and the main thread asks the developer.
- The agent that wrote the code never signs it off. At tier 2 and above, `verifier` decides whether it works.
- Name the exact files in every brief. The tree holds unrelated uncommitted work, so reviewers must not review the whole diff.
- You own the result: check an agent's work and write your own summary.

## 5. Review

Don't repeat a review that already covered the same diff, and skip all of it at tier 0. Use `/security-review` for any diff touching uploads, credentials, storage, CORS or spreadsheet parsing, at any tier. Reviewers report; the main thread decides. Treat restructuring advice as optional unless it fixes a defect, and never let it override AGENTS.md rule 9 or section 5.1.

## 6. Report

End with what changed, the evidence (commands and results), outstanding risks, suggested next steps, and the AGENTS.md 5.9 items.
