You pick up the next available task from the HexCrawl board. You fetch the latest code, check for open questions the developer still needs to answer, find an unclaimed task, verify no one else is working on it, create a branch, and push it — so the user can then run `/implement` to do the actual work.

**Argument:** $ARGUMENTS (task ID like `1.3`, or empty to auto-pick the next eligible task)

## Deliverables

This command produces:
- A list of any **open questions** the developer should answer before picking up new work (from `QUESTIONS.md` and/or `❓` markers in `BOARD.md`).
- A local branch checked out and pushed to remote, named after the picked task.
- A short summary of what was picked and why, so the user knows what to run next (`/implement`).

## Scope Boundaries

**You MUST NOT:**
- Write or modify any source code, `BOARD.md`, `QUIZZES.md`, `CLAUDE.md`, `QUESTIONS.md`, or any task notes file.
- Start implementation — that's `/implement`'s job.
- Create new tasks on the board.
- Answer open questions on the user's behalf. Surface them; let the human decide.

**You MUST:**
- Read `CLAUDE.md`, `BOARD.md`, and (if present) `QUESTIONS.md` to understand status and blockers.
- Check remote branches to avoid collisions.
- Create and push the branch before finishing.

## Workflow

### Step 1: Fetch latest

```
git checkout main && git pull
```

### Step 2: Read the board + CLAUDE.md

Read `CLAUDE.md` for stack and conventions, then `BOARD.md` for task statuses. Tasks are numbered `<phase>.<n>` (e.g. `1.3`, `2.7`). Statuses use emojis: `🔲 backlog` · `🔄 in progress` · `✅ done` · `🚫 blocked`.

### Step 3: Check for open questions

Surface anything the developer still owes an answer on. Check these sources **in order** and stop asking the user once you've collected the full list:

1. `QUESTIONS.md` at repo root, if it exists. Parse Markdown checkbox items:
   - `- [ ] ...` → open question
   - `- [x] ...` → answered (ignore)
2. `BOARD.md` — any line containing the `❓` marker is treated as an unresolved question attached to that row.
3. Any file under `board/tasks/` (if that directory exists) with a `## Open Questions` or `## Open Questions / Risks` section containing bullets that are not struck through (`~~...~~`) or marked `[resolved]`.

If any open questions are found:

- List every one with its source (file + line) and the task ID it blocks, if any.
- Tell the user: "Answer these before I create a branch, or say 'proceed anyway' to pick up the task regardless."
- Wait for the user's response. If they say proceed, continue; otherwise stop here.

If no open questions, say "No open questions — proceeding." in one line and continue.

### Step 4: Select a task

If a task ID was provided (`$ARGUMENTS`), use that task. Validate it exists and has status `🔲 backlog`.

If no argument was provided, auto-pick by:

1. Collect all tasks with status `🔲 backlog`.
2. Exclude tasks whose **phase gate** is not cleared: a task in Phase N is eligible only if the Phase (N−1) summary quiz is `🏆` (per `BOARD.md` → "Quiz system"). Phase 1 has no gate.
3. Within the earliest eligible phase, pick the task with the **lowest ID** (1.1 before 1.2 before 1.3). The board is already dependency-ordered within a phase.
4. If nothing is eligible (e.g. Phase 1 quiz not yet passed and Phase 1 is fully done), explain what's blocking and list the blocker (e.g. "Phase 1 quiz still `⬜` — run `/quiz phase 1` before picking up Phase 2 work").

### Step 5: Check for collisions

Run `git branch -r` to list all remote branches.

- For task `<id>`, check if any branch matching `*<id>-*` or `*<id>/*` exists on remote (e.g. `feat/1.3-*`).
- If a matching branch exists, someone may already be working on this task. **Do NOT create a duplicate branch.** Inform the user and suggest either checking out the existing branch or picking a different task (back to Step 4, excluding this task).
- Also check `BOARD.md` for the task's status cell. If it is already `🔄 in progress`, flag it — the branch may exist under a different name or someone forgot to push.

### Step 6: Create and push branch

Branch name format (per `CLAUDE.md` → "Code conventions" which mandates `feat/` / `fix/` / `chore/` prefixes):

- Default prefix: `feat/` for all new tasks from the board.
- Use `fix/` only if the task itself is a bug-fix task (its title starts with "fix" or the BOARD row describes a defect).
- Use `chore/` for infra / tooling / docs-only tasks (Phase 6 deploy tasks, Dockerfile tweaks, etc. — judge from the task title).

Full format: `<prefix>/<id>-<short-slug>`

- `feat/1.3-enemy-dataclass`
- `feat/2.7-redis-cache`
- `chore/6.4-github-actions-ci`

The slug should be 2–4 words, lowercase, hyphen-separated, derived from the task title in `BOARD.md`.

```
git checkout -b <branch-name> main
git push -u origin <branch-name>
```

### Step 7: Summary

Tell the user:
1. Task picked (ID, title, phase).
2. Branch name created and pushed.
3. Any open questions that were surfaced and whether they were acknowledged.
4. Next step: `/implement` (to build it) — and remind them that `/quiz <id>` follows after the task is done.

## Important Rules

- Do NOT proceed past Step 6 into any implementation work.
- Do NOT modify any files. This command only reads files and does git operations.
- If `$ARGUMENTS` specifies a task that doesn't exist or isn't `🔲 backlog`, say so and stop.
- If there are no eligible tasks (phase gate blocking, or all `✅ done`), explain clearly — list what's blocking and what quiz / task needs to happen first.
- Always push the branch before finishing. The pushed branch is the public claim.
- Never invent an open question or mark one as resolved. Surface the text verbatim.
