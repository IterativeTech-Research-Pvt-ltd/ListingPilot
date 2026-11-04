# ListingPilot — Claude Code

@AGENTS.md

## Claude Code only

- Skills: `.agents/skills/` is the library. Claude Code doesn't discover it directly, so `.claude/scripts/sync-skills.mjs` links the non-plugin skills into the git-ignored `.claude/skills/` at session start. Ponytail and pstack arrive as plugins. Never edit `.claude/skills/` by hand. See AGENTS.md sections 6–10 for when to use them.
- Routing, tiers and agents: `.claude/rules/orchestration.md`. Setup, verification and known limits: `docs/CLAUDE_CODE_SETUP.md`.
- Per-diff review: the built-in `/code-review` and `/security-review`. The `security` skill is for repo-wide audits.
- `python-backend-expert` and `security` run as forked subagents (`context: fork`). Give them the AGENTS.md rules that apply to their task.
- Browser checks: Claude in Chrome against http://localhost:3000, with the backend on :8000. Don't click anything that opens alert or confirm dialogs.
