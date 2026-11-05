# Claude Code setup for ListingPilot

How Claude Code is configured to work from an outcome you describe, what it enforces, and what it can't do. `AGENTS.md` stays the source of project rules; this explains the machinery around it.

## How a request gets routed

1. **Rules load.** `CLAUDE.md`, `AGENTS.md` and `.claude/rules/*.md` are in context at the start of every session and every custom subagent.
2. **Claude triages.** `.claude/rules/orchestration.md` sorts the request into a tier, which sets the plan, delegation and review.
3. **Skills load on demand.** Claude sees only each skill's name and description, and pulls in the full text when one fits. AGENTS.md sections 7–9 say which fits and how its advice is overridden.
4. **Hard limits apply throughout.** Permission rules and the guard hook run on every shell command, in subagents too.

| Tier | Looks like | Plan | Review after |
| --- | --- | --- | --- |
| 0 | Question, typo, docs-only edit | None | None |
| 1 | Small bug or behaviour change | None | `/code-review low` |
| 2 | Multi-file fix or small addition to something that exists | Short plan, then continue | `verifier`, `/code-review`, `ponytail-review` |
| 3 | A new feature or workflow; schema, export gate, credentials, storage, AI prompts; more than about 3 commits | Plan, then wait for approval | Tier 2 plus `security-reviewer`, `code-quality-reviewer`, and `architect` beforehand |

When unsure between tier 2 and tier 3, Claude chooses tier 3. Routing is an instruction Claude follows, so it can still misjudge a tier. Only the limits under [Enforced limits](#enforced-limits) are guaranteed.

## Skills

`.agents/skills/` is the canonical library, pinned in `skills-lock.json`. Claude Code v2.1.312 doesn't read that folder, so it reaches the 92 skills in three ways:

| Group | Count | Route |
| --- | --- | --- |
| AGENTS.md section 7 skills | 22 | Linked, listed to Claude, auto-selected |
| Thermos | 1 | Linked as a `/` command; `code-quality-reviewer` reads its file |
| AGENTS.md section 10 skills | 4 | Linked, developer-only (`user-invocable-only`) |
| `using-superpowers` | 1 | Linked but `off`: its "1 % rule" conflicts with section 9 |
| pstack | 58 | Plugin, as `/pstack:<name>`; not linked, or each would appear twice |
| Ponytail | 6 | Plugin, as `/ponytail:<name>`; not linked |

Nearly all of pstack, and Thermos, set `disable-model-invocation`. The Skill tool refuses them and `skillOverrides` can't lift that (tested). So `orchestration.md` lists the few worth using automatically, and Claude reads those files directly, which is the route pstack documents for Claude Code.

### The link script

`.claude/scripts/sync-skills.mjs` runs at every session start and creates the links in the git-ignored `.claude/skills/`. Windows symlinks need Developer Mode or admin rights; junctions need neither.

```bash
node .claude/scripts/sync-skills.mjs          # create or repair links
node .claude/scripts/sync-skills.mjs --check  # report drift, change nothing
```

It reads `skills-lock.json`, so a newly installed skill is linked automatically unless it comes from pstack or Ponytail. It changes only link entries directly inside `.claude/skills/`, verifies every target resolves inside `.agents/skills/`, has no recursive delete, and creates each link under a temporary name before renaming it, so a killed run can't leave a half-made skill. Anything it can't prove it owns is reported and left alone.

Junctions are per machine and aren't stored in git. A fresh clone or `git clean` loses them, and the next session recreates them. A new session is needed for new links to load. If you move the repo, the old links point outside the library: the script refuses to touch them, so delete them with `rmdir` and run it again.

## Plugins

Both are enabled for this project in `.claude/settings.json`. Their files live in your user plugin cache.

| Plugin | Version | Provides | Reviewed behaviour |
| --- | --- | --- | --- |
| `ponytail@ponytail` | 5.3.3 | 6 skills, 3 hooks, a status band | No PreToolUse hook and no permission decisions. The band's tool handler only observes. No network unless a webhook is set. |
| `pstack@cursor-plugins` | 0.15.36 | 58 skills, 2 agents | No hooks, MCP servers or tool grants. Of its skills, 34 match `.agents/skills/` exactly; 24 differ only in adapter wording. |

**Thermos has no Claude Code plugin.** It's Cursor-only, so `code-quality-reviewer` applies the installed skill instead. Its separate bug-and-security pass isn't installed; `/code-review` and `/security-review` cover that ground.

Ponytail settings:

- `PONYTAIL_DEFAULT_MODE=full` in project `env`.
- `PONYTAIL_SUBAGENT_MATCHER` limits it to the three implementers, so reviewers and the verifier aren't told to be lazy.
- `ledger=false`, stored in `pluginConfigs` in `~/.claude/settings.json`, stops the per-turn cost log.
- An empty `~/.claude/.ponytail-statusline-nudged` stops it asking Claude to offer edits to your user settings.

Measured context cost per session, on a base of about 53,600 tokens: Ponytail about 2,300, pstack about 340. `claude plugin details` says 4,802 for pstack because it counts skills that are hidden from the model.

### Model routing

`.claude/rules/pstack-models.md` holds pstack's role settings at the `medium (high)` budget: `sonnet high` for coding and exploring, `opus high` for judgment, and both for panels. Opus, Sonnet and Haiku were confirmed on 4 Nov 2026. Fable is left out because the account has no usage credits for it, and no non-Claude model is available, so Arena's cross-judge can't leave the Claude family.

Edit that file directly. Rerunning `/pstack:setup-pstack` writes a second, user-level file.

## Specialist agents

Defined in `.claude/agents/`. Each receives `CLAUDE.md`, `AGENTS.md` and the rules automatically, and its own file adds only role-specific limits.

| Agent | Model | Access |
| --- | --- | --- |
| `backend-engineer` | Sonnet | Writes; targeted pytest |
| `frontend-engineer` | Sonnet | Writes |
| `database-supabase` | Opus | Drafts migrations; can't apply them |
| `verifier` | Sonnet | Runs the full suite and read-only browser checks; can't edit or click |
| `architect` | Opus | Read-only |
| `security-reviewer` | Sonnet | Read-only |
| `code-quality-reviewer` | Opus | Read-only |

The agent that wrote the code never signs it off. Agents don't use worktrees, because a worktree branches from HEAD and would miss uncommitted work.

## Enforced limits

Two layers run on every call, including inside subagents, and they hold under `bypassPermissions`:

- **`.claude/settings.json`**: `deny` rules for the Read and Edit tools, and `ask` rules for plain git, install and database commands.
- **`.claude/hooks/guard-bash.mjs`**: parses each shell command, so variants like `git -C . commit`, `bash -c "..."`, `$(...)`, `xargs` and `python -m pip` are caught. If the hook crashes, `onFailure: block` stops the command rather than letting it through.
- **`.claude/hooks/guard-browser.mjs`**: default-deny for Claude in Chrome in subagents. They can read pages, take screenshots and open the frontend, and nothing else.

| Outcome | What |
| --- | --- |
| Denied | `git add -A` and other broad staging, `commit -a`, `reset --hard`, `clean`, `stash`, `checkout --`, `restore`, forced pushes, history rewrites; reading or writing `.env` and credential files; writing to the official templates, `.agents/skills/`, `.claude/skills/` or `skills-lock.json`; a second pytest session; pytest from an agent other than `verifier` or `backend-engineer` |
| Needs approval | Other git writes; dependency installs; `npx`; `alembic`, `psql`, `supabase`; the seed script; anything using `DATABASE_URL`; Supabase HTTP calls; starting the backend; write requests to the local backend, including `GET /meesho/export`; inline scripts that reach the database or backend; recursive or wildcard deletes; plugin and MCP changes |
| Denied for subagents | Everything in "Needs approval". Approval only happens on the main thread, because a prompt raised by a background agent is easy to accept without context. Also every browser action except reading, and navigation anywhere but the frontend |

To run something denied, type it yourself or prefix it with `!` in the prompt.

**Why the local app needs this.** It runs on the real database. `GET /meesho/export` marks drafts exported and commits, so a plain URL visit changes data. Starting the backend runs `create_all`. Page load itself is safe: it makes 8 kinds of GET request and nothing else.

**What the guard can't see.** It stops mistakes, not an adversary. A script written to a file and then run, a command held in a shell variable, and a git alias all get past it. **Clicks on the main thread aren't enforced**: only subagents are blocked, so the main thread relies on the rule in `orchestration.md`. Interactive UI checks are therefore never automatic: `verifier` reports them as NOT VERIFIED and the main thread asks you. The guard matches paths by pattern, so it blocks writes to a `.agents/skills/` path in any repo, not just this one. `Bash(git stash *)` also catches the read-only `git stash list`, which costs an extra prompt and nothing else. Killing a session can leave its pytest running; the one-session guard then makes the next run wait.

## Verifying the setup

```bash
node --test ".claude/hooks/*.test.mjs" ".claude/scripts/*.test.mjs"
node .claude/scripts/sync-skills.mjs --check
claude plugin list
```

In a session, `/doctor` and `/context` show what loaded, and `/skills` shows or changes skill visibility.

### Results from 4 Nov 2026

| Check | Result |
| --- | --- |
| Skill discovery | From 0 to all 22 auto-listed; the 4 developer-only skills and Thermos available as commands; `using-superpowers` hidden |
| Guard and sync tests | 278 of 278 passed; 26 of 26 deliberate breakages caught |
| Guard in real sessions | Prohibited commands blocked on the main thread (auto mode) and in subagents (`bypassPermissions`), including `frontend-engineer`, in sandbox repos; their commits, staging, stash and uncommitted edits were unchanged |
| Approval prompt | One observed test: the developer chose No on a prompt, the tool use was rejected, and the command's marker file was never written. Earlier prompts are inconclusive: the record doesn't show what was physically chosen |
| One pytest at a time | Denied while a session ran; of two simultaneous starts, one got through |
| Verifier and the real app | Clicks, typing, keys, form input, JavaScript and navigation to the backend all refused in a real browser. POST to the backend and starting the backend refused. Page load makes GET requests only. `/drafts` was unchanged |
| Routing | 23 runs on the final rules. 9 of 9 substantial-feature runs chose tier 3 with plan approval, and no small change over-escalated. 21 were scored as passes; the other 2 behaved correctly (one stopped before giving a tier, one asked about a label that doesn't exist) |
| Real task | A read-only Opus audit of the export gate: 56 turns, about 30 minutes, $5.14. Repo and database snapshots were identical before and after |

The routing scenarios ran on Sonnet in plan mode, so they show what Claude loaded and said it would do, not a full implementation. Plan approval is an instruction, not an enforcement: nothing stops a session from misjudging a tier.

## Manual setup and known gaps

- **Fable** needs usage credits. Add them, then update `pstack-models.md` if you want it.
- **`gh` and `bun`** aren't installed, so pstack's PR and script workflows are skipped.
- **Playwright** isn't installed, so browser checks use Claude in Chrome. `webapp-testing` needs it.
- **Alembic** isn't set up, so schema tasks stop and raise that first.
- **Supabase MCP** isn't configured, by choice: Alembic owns the schema.
- **Taplio** needs authorizing in claude.ai connector settings, but nothing here uses it.
- **The Ponytail band** is a terminal feature. With the ledger off it shows live numbers only.
