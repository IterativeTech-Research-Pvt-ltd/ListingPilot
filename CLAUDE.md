# ListingPilot — Claude Code

@AGENTS.md

## Claude Code only

- Skills load from `.agents/skills/`, the single skill directory. Never create `.claude/skills/` or symlink skills into it. See AGENTS.md sections 6–10 for when to use them.
- Per-diff review: the built-in `/code-review` and `/security-review`. The `security` skill is for repo-wide audits.
- `python-backend-expert` and `security` run as forked subagents (`context: fork`). Give them the AGENTS.md rules that apply to their task.
- Browser checks: Claude in Chrome against http://localhost:3000, with the backend on :8000. Don't click anything that opens alert or confirm dialogs.
