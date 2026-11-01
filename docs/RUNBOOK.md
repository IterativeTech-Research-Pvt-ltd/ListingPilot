# RUNBOOK — Running the Autonomous Build

This document has two audiences:

- **Sections 1 to 4** are for the person who sets up the machine and starts Claude Code.
- **Sections 5 to 7** are for Claude Code itself.

## 1. Machine requirements

| Item                 | Requirement                                                                                                                                                                                                |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Operating system     | Linux or macOS. On Windows, use WSL2 with Ubuntu and keep the repository inside the Linux file system                                                                                                      |
| Docker               | Docker Engine or Docker Desktop with Compose, running before the build starts                                                                                                                              |
| Python               | Version 3.12                                                                                                                                                                                               |
| Node.js              | Current long-term-support release, with npm                                                                                                                                                                |
| Git                  | Installed and configured with a name and email                                                                                                                                                             |
| Browsers for testing | Installed by Claude Code during milestone M0 through Playwright's browser installer                                                                                                                        |
| Disk and memory      | At least 20 GB free disk and 8 GB memory                                                                                                                                                                   |
| Network              | Outbound access to Amazon's SP-API and Login with Amazon, Flipkart's API and Seller Hub, the Meesho supplier panel, Anthropic's API, the storage provider, Neon, and the Python and npm package registries |
| Isolation            | A dedicated machine, virtual machine or container. Claude Code will run commands without asking, so the machine should hold nothing else of value                                                          |

## 2. Preparing the repository

1. Create an empty folder and initialise a Git repository in it.
2. Place in the folder root:
   - CLAUDE.md
   - RUNBOOK.md
3. Create a docs folder containing:
   - PRD.md
   - SRS.md
   - SPEC_ADDENDUM.md
   - BUILD_PLAN.md
   - TEST_PLAN.md
   - HUMAN_HANDOFF.md
4. Inside docs, put any Meesho templates into docs/meesho/templates and the Meesho category file into docs/meesho/categories. Put any Flipkart vertical templates into docs/flipkart/templates.
5. Create the .env file in the root with every value listed in HUMAN_HANDOFF section A and SPEC_ADDENDUM section 3.
6. Put the seller's catalogue spreadsheet and photos into data/pilot (see SPEC_ADDENDUM section 1 for photo naming).
7. Make the first commit containing only the documents and templates. Never commit .env or data/pilot.

## 3. Starting Claude Code

1. Open a terminal in the repository root and start Claude Code.
2. Turn off permission prompts (Claude Code's skip-permissions option), so it can edit files and run commands unattended. Do this only on the isolated machine from section 1.
3. Give it this single instruction:
   "Read CLAUDE.md and RUNBOOK.md, then follow them until every item in the BUILD_PLAN definition of done is complete."
4. Leave it running.

## 4. The person's daily routine (about five minutes)

- If the Claude Code session has ended, start a new one with the same single instruction. Nothing else is needed; the session protocol in section 5 makes it resume where it stopped.
- Read the last lines of docs/PROGRESS.md to see what was done.
- Check section B of docs/HUMAN_HANDOFF.md for open items. The only one expected to need you is the Meesho one-time login (run the login command, log in normally, close the browser).
- Do not edit code or answer questions; there should be none.

## 5. Session protocol (for Claude Code)

### At the start of every session

1. Read, in order:
   - CLAUDE.md and this runbook;
   - the last 40 lines of docs/PROGRESS.md;
   - all of docs/DECISIONS.md;
   - the open items in docs/HUMAN_HANDOFF.md.
2. Start the services and run the full check. If anything fails, fix it before any new work. A failing state left by an interrupted session is the first task.
3. Find the first unfinished task in the BUILD_PLAN, and continue from there.

### During the session

- Finish one task at a time. Commit after each task, with the progress log updated.
- Never leave uncommitted work for longer than one task.
- When the session context is getting long:
  - finish the current task, or bring it to a clean stopping point;
  - commit;
  - add a progress line beginning "NEXT:" that names the exact next step.

### At the end of the session

- All tests are green.
- Everything is committed.
- The progress log says what comes next.

## 6. Handling time

- Follow the BUILD_PLAN dates as targets, not stop conditions.
- If a milestone runs past its end date, apply the cut order in BUILD_PLAN section 4 for the remaining milestones. Record the cut in DECISIONS.
- After the definition of done is met, stop adding features. Spend remaining time only on fixes, tests and documentation.

## 7. When to stop

The build is complete when:

- every box in the BUILD_PLAN definition of done is checked;
- the final full green gate log is saved in the artifacts folder;
- the last progress line reads "BUILD COMPLETE", with the date.
