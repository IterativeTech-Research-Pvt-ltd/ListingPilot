# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# Project-level on purpose: rerunning /pstack:setup-pstack writes a separate user-level file, so edit this one instead.
# Values are `<model> <effort>` for the Agent tool. Verified 4 Nov 2026: opus, sonnet and haiku work. fable is left out because the account has no usage credits for it. No non-Claude model is available.
# budget: medium (high)
feature, refactoring: sonnet high
bug-fix: sonnet high
perf-issue: sonnet high
hillclimb: sonnet high
judgment and prose: opus high
hardest tasks: opus high
how explorer: sonnet high
how explainer: opus high
why investigators: sonnet high
why synthesizer: opus high
reflect tooling: sonnet high
reflect judgment, divergent, synthesizer: opus high
arena runners: opus high, sonnet high
arena cross-judge pool: opus high, sonnet high
swarm workers: sonnet high
architect runners: opus high, sonnet high
interrogate reviewers: opus high, sonnet high
