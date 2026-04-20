You are debugging a bug collaboratively with the human. Your job is to systematically gather information, form hypotheses, test them, and fix the bug.

**Argument:** $ARGUMENTS — either a task ID (e.g. `1.3`) or a bug file name (e.g. `websocket-disconnect` → reads `bug/websocket-disconnect.md`). Required.

## Input Modes

1. **Task ID** (matches pattern `\d+\.\d+[a-z]?`): reads the task row from `BOARD.md`. Bug investigation file goes to `bug/<id>.md` (e.g. `bug/1.3.md`).
2. **Bug file name** (anything else): reads the user's bug description from `bug/<name>.md`. This file should contain a freeform description of the bug (symptoms, context, steps to reproduce — whatever the user wrote). Investigation continues in the same file.

## Deliverables

- A bug investigation file at `bug/<id_or_name>.md` (created or updated in place).
- The fix itself (source code changes).
- Updated `BOARD.md` (task status → `✅ done`) — only when the input was a task ID **and** the fix closes that task. The quiz cell is never touched.

## Scope Boundaries

**You MUST NOT:**
- Guess at the root cause without evidence — form hypotheses and verify them.
- Ask the user for information you can gather yourself (logs, code inspection, DB queries, Redis state).
- Ask a question whose answer is already recorded in the bug file.
- Fix unrelated issues — stay on the bug.
- Cross a hexagonal boundary to apply the fix. If the only fix requires importing a framework into `src/domain/` or `src/application/`, stop and surface the design question.

## Phase 1: Setup

1. Parse `$ARGUMENTS`. If missing, ask the user.
2. Determine input mode:
   - Matches `\d+\.\d+[a-z]?` → **Task ID mode**: read the matching row in `BOARD.md`.
   - Otherwise → **Bug file mode**: read `bug/<name>.md`. If the file doesn't exist, tell the user and stop.
3. Create the `bug/` directory if needed. Read or create the investigation file at `bug/<id_or_name>.md` using the template below.
4. In bug file mode, populate `## Symptoms` and `## Steps to Reproduce` from the user's description.
5. If the investigation file already exists, read it fully — **do not re-ask anything already recorded there**.
6. Read `CLAUDE.md` to understand the layer the bug likely lives in (hexagonal rules, WebSocket turn loop, Celery tasks, etc.). This often tells you where to look first.

## Phase 2: Information Gathering

Loop until you have enough to form a hypothesis:

1. **Before asking the user anything**, check what you can gather yourself:
   - Read relevant source code (Grep/Glob/Read). Start in the layer `CLAUDE.md` implicates for the observed symptom (e.g. "WebSocket disconnects mid-turn" → `src/entrypoints/ws/` and `src/application/process_turn.py`).
   - Inspect running infrastructure if available:
     - Postgres via `psql $DATABASE_URL` or the configured SQLAlchemy session — query relevant tables, check migration state with `alembic current`.
     - Redis via `redis-cli -u $REDIS_URL` — check keys matching the affected session, check TTLs.
     - Application logs (`structlog` output — grep the log stream for the session id / user id).
     - Celery worker logs and the result backend, if a task is implicated.
     - Docker: `docker compose logs <service>` for the local stack.
   - Run focused tests that should already cover the bug path: `pytest tests/unit/... -k <keyword>` or the matching integration test. A failing test narrows the hypothesis sharply.
   - Re-run the last failing command the user reported with `-vv` / extra logging.
2. Record every new finding in the bug file under `## Gathered Info` with a dated subsection. Include exact commands run, file:line references, and log snippets.
3. If you need something only the user can provide (browser console output, visible UI behaviour, screenshots, precise reproduction steps), ask clearly — explain **what hypothesis this tests**.
4. When the user provides info, immediately append it to the bug file.

## Phase 3: Hypotheses

1. List hypotheses in the bug file under `## Hypotheses`.
2. For each hypothesis, note:
   - What evidence supports it (cite log lines, file:line, test output).
   - How to confirm or rule it out (a concrete command, test, or inspection).
   - Status: `untested` → `testing` → `confirmed` / `ruled out`.
3. Test hypotheses one at a time. Update the bug file after each test.
4. Bias hypotheses toward the places HexCrawl bugs concentrate:
   - **Hexagonal leak**: domain or application accidentally depending on an adapter, causing surprising test behaviour.
   - **Redis / Postgres desync**: game state updated in one but not the other, especially across floor-descent checkpoints.
   - **WebSocket lifecycle**: auth on connect, message framing, disconnect cleanup, race between two turns.
   - **Async misuse**: missing `await`, sync DB call inside async route, Celery task awaited inline.
   - **Celery idempotency / Beat timing**: double-runs of `score_recalc`, timezone mistakes on `weekly_leaderboard`.
   - **Seed determinism**: `DungeonGenerator` using global `random` instead of a seeded instance.
   - **Pydantic/dataclass boundary**: a Pydantic schema leaking into domain or vice-versa.

## Phase 4: Fix

1. Once the root cause is confirmed, describe it in the bug file under `## Root Cause` — include the offending file:line and what was wrong.
2. Implement the fix. Keep it minimal — address the root cause, not surrounding code.
3. Add a regression test at the correct tier (unit/domain if domain logic, integration/adapter if infrastructure, e2e/ws if the WebSocket lifecycle). The test must fail on the old code and pass on the fix — verify this.
4. Commit with a Conventional Commit message referencing the bug/task:
   - Task ID mode: `fix(<scope>): <one-line> (<id>)`
   - Bug file mode: `fix(<scope>): <one-line> (bug/<name>)`
5. Describe the fix in the bug file under `## Fix Applied`, listing changed files and the regression test that covers it.
6. Ask the user to verify the fix (retest in UI / rerun the failing scenario / exercise the WebSocket path).

## Phase 5: Wrap-up

1. Once the user confirms the fix works:
   - Update bug file status to `RESOLVED`.
   - If Task ID mode and this fix closes the task, update `BOARD.md` — flip the status cell from `🔄 in progress` (or `🔲 backlog`) to `✅ done`. Leave the quiz cell as-is.
2. If the user reports the fix didn't work, go back to Phase 2 — append new findings to `## Gathered Info`, do not overwrite.

## Bug File Template

When creating a new bug file, use this structure:

```markdown
# <id_or_name>: <title from BOARD.md row or bug file>

**Status:** INVESTIGATING | HYPOTHESIS | FIX_APPLIED | RESOLVED
**Reported:** <date>
**Severity:** <from BOARD.md notes, bug file, or ask user>
**Source:** <task id (e.g. 1.3) or bug file (e.g. bug/websocket-disconnect.md)>
**Suspected layer:** <domain | application | adapters | entrypoints | frontend | infra | unknown>

## Symptoms
<What the user observes — fill from task description, bug file, or ask>

## Steps to Reproduce
1. <Fill from task, bug file, or ask user>

## Gathered Info
<!-- Append-only. Never delete previous findings. Each entry dated. -->

## Hypotheses
<!-- Track each hypothesis with status -->

## Root Cause
<Filled when confirmed — include file:line>

## Fix Applied
<Filled when implemented — list file:line changes and the regression test>
```

## Rules

- **The bug file is append-only for Gathered Info.** Never delete previous findings. Only update status fields and add new sections.
- **Always explain why you're asking.** Every question to the user must state which hypothesis it tests or what information gap it fills.
- **Try automated tools first.** Fall back to asking the user only when the information is not programmatically accessible (UI behaviour, visual glitches, browser state, something happening on the user's machine).
- **One hypothesis at a time.** Don't shotgun — test systematically.
- **Record everything.** If you discover something (even if it rules out a hypothesis), write it down. This persists across sessions.
- **Respect hexagonal boundaries.** If the fix path seems to require a forbidden import, stop — the design is wrong and needs the user's input, not a workaround.
