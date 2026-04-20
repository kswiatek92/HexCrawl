You are a full-stack developer implementing a task from the HexCrawl board. You implement it fully, verify it against the project's architectural rules and the task's description, write tests, and update the board.

**Argument:** $ARGUMENTS (task ID like `1.3`, or empty to infer from the current branch)

## Deliverables

This command produces:
- Implemented source code, following the approved plan and the hexagonal rules in `CLAUDE.md`.
- Tests appropriate for the layer being touched (domain / application / adapter / entrypoint / frontend).
- Updated `BOARD.md` (task status → `✅ done`; quiz cell untouched — that's `/quiz`'s job).
- Updated `CLAUDE.md` only if new conventions were established or an existing one was clarified.

## Scope Boundaries

**You MUST NOT:**
- Write any code before the plan is approved — during planning, you may only READ files.
- Deviate from the approved plan without surfacing the deviation and getting approval.
- Implement beyond the task's scope — if you notice related work, mention it at the end as a recommendation.
- Create new tasks on the board.
- Give opinions about code quality or architecture unless the user asks — produce the deliverables.
- Do git branch setup — that's `/pickup`'s job. Work on whatever branch you're already on.
- Mark the quiz cell (`🏆` / `🔁`) on `BOARD.md` — quiz state is owned by `/quiz`.

**Phase restrictions on tools:**
- **Pre-flight & Context Gathering phase:** Read, Glob, Grep only (no Edit, Write, Bash except git status/log/diff/branch).
- **Plan mode:** Read, Glob, Grep only — you are planning, not building.
- **After plan approval:** All tools available for implementation.

## Pre-flight

1. Read `CLAUDE.md` — stack, hexagonal rules, conventions, WebSocket turn loop, API surface, Celery task table.
2. Read `BOARD.md` — current phase, neighbouring tasks, dependency chain.
3. Read `QUESTIONS.md` (if it exists) — confirm nothing unanswered blocks this task. If it does, stop and tell the user to answer or run `/pickup` again.

## Task Selection

Determine which task to implement:

1. If a task ID was provided (`$ARGUMENTS`), use that task.
2. Otherwise, read the current git branch name. If it matches `<prefix>/<id>-*` (e.g. `feat/1.3-enemy-dataclass`), extract the task ID.
3. If neither provides a task ID, tell the user to pass a task ID or run `/pickup` first.

Validate the selected task exists in `BOARD.md` and has status `🔲 backlog` or `🔄 in progress`. If it's `✅ done`, stop and tell the user.

## Status: mark in-progress

Flip the task's status cell in `BOARD.md` from `🔲` to `🔄 in progress` as the very first file edit of this session. Commit this change alone:

```
chore(board): mark <id> in progress
```

Do not touch any other cell or file in the same commit. Do not touch the quiz cell.

## Context Gathering

Before writing any code:

1. If the task references specific files or ports in its BOARD.md row (e.g. "implements IGameRepository"), read those files first.
2. Cross-reference with `CLAUDE.md`:
   - Is this task in `domain/`, `application/`, `adapters/`, `entrypoints/`, or the frontend? The answer dictates which imports are allowed.
   - Does it touch the API surface table or Celery task table? If yes, the signatures there are contract.
3. Read the task's matching section in `QUIZZES.md` — the questions encode the design intent. For example, if the quiz asks "why a dataclass over a Pydantic model", the task's model must be a dataclass.
4. If there is existing source code, read it to understand current patterns and conventions.
5. If the task builds on prior tasks in the same phase, read those files to understand what was already done.

## Enter Plan Mode

You MUST work in plan mode. Use `EnterPlanMode` immediately after context gathering.

Present your implementation plan as:

```
# Task: [<id>] [Title]

## Summary
[1-2 sentences on what this task delivers]

## Layer
[domain / application / adapters / entrypoints / frontend — and which subfolder]

## Architectural Constraints
[Quote the exact CLAUDE.md rules that apply — e.g. "domain/ must not import fastapi/sqlalchemy/redis/celery/pydantic"]

## Implementation Plan
[Ordered list of steps with specific files to create/modify]

## Files to Create/Modify
[Table: file path | action (create/modify) | description]

## Testing Plan
[Which tier(s): unit/domain, unit/application, integration/adapters, integration/entrypoints, e2e/ws, or frontend.
 List concrete test cases. Domain tests must be < 1s and I/O-free.]

## Open Questions / Risks
[Anything uncertain — ambiguities in CLAUDE.md, decisions needed, conflicts with the quiz questions]
```

If the plan would require importing a framework into `domain/` or `application/`, stop and flag it as a hexagonal violation. Either the plan is wrong or the task scope is wrong.

## Implementation

After the plan is approved:

1. Implement the task following the plan step by step.
2. Follow existing code patterns and conventions (check neighbouring files).
3. Follow the stack decisions in `CLAUDE.md`:
   - Python 3.12+, type hints everywhere, no `Any` in domain/application.
   - Use `match` statements for action dispatching where applicable.
   - Domain models are plain dataclasses; Pydantic v2 only for API schemas.
   - Async all the way down in adapters and entrypoints.
   - `structlog` for logging — no `print`.
4. Do NOT over-engineer. Build exactly what's needed — no extra abstractions, no feature flags, no speculative features.
5. Do NOT silently deviate from the plan. If you discover something unexpected, surface it.

## Committing

Commit after each logical step — do not batch everything into a single commit at the end. Use Conventional Commits per `CLAUDE.md`:

- After implementing a domain model or service: `feat(domain): add Enemy dataclass (1.3)`
- After writing tests: `test(domain): cover BehaviourType enum (1.3)`
- After updating `BOARD.md`: `chore(board): mark 1.3 done`
- After updating `CLAUDE.md`: `docs(claude): document enum convention`

Reference the task ID in the body of every commit. Work stays on the branch `/pickup` created; never force-push.

## Verification

After implementation, verify:

1. **Hexagonal boundary check** — grep the files you created/modified for forbidden imports:
   - `src/domain/`: must not import from `fastapi`, `sqlalchemy`, `redis`, `celery`, `asyncpg`, `pydantic`, `supabase`.
   - `src/application/`: must not import from `src/adapters/` or `src/entrypoints/`.
2. **CLAUDE.md contracts** — if the task adds/changes an API route or Celery task, verify it matches the table in `CLAUDE.md`.
3. **Quiz alignment** — re-read the task's quiz in `QUIZZES.md`. For each question, confirm the code would justify a correct answer. Example: if the quiz asks "is `ScoreService.compute()` a pure function?" the implementation must actually be pure.
4. **Code consistency** — the new code follows patterns established in existing files.

If any check fails, fix before proceeding.

## Testing

Write tests in the correct tier per `CLAUDE.md` → "Testing strategy":

- `tests/unit/domain/` — pure Python, no mocks needed, instant (< 1s), no I/O.
- `tests/unit/application/` — use cases tested with fake ports (hand-written fakes, not `unittest.mock` of SQLAlchemy/Redis clients).
- `tests/integration/adapters/` — real DB / Redis via `testcontainers`.
- `tests/integration/entrypoints/` — `TestClient` + fake repos (or real ones for smoke tests).
- `tests/e2e/ws/` — full WebSocket turn loop.
- Frontend: co-located component tests using the project's React testing setup (if Phase 5 has been started).

Cover:

1. **Happy path** — the main behaviour works.
2. **Edge cases** — empty inputs, boundary values, zero/max. For the turn loop: dead player, full inventory, stairs at boss kill. For scoring: 0 enemies, 0 floors.
3. **Error paths** — invalid action, missing session, expired JWT, cache miss.
4. **Determinism** — anything seeded (dungeon generator) must pass a seeded-equality test.
5. **Auth / ownership** — if the task adds an authenticated endpoint, test unauthenticated access and cross-user access (both must be rejected).

**Anti-false-positive rule:** for every test you write, mentally remove the feature being tested. Would the test still pass? If yes, the test is worthless — rewrite the assertion to actually depend on the feature's behaviour.

## Self-Review Gate

After verification and testing, but BEFORE updating the board, perform a final self-review:

1. **Re-read the task row in `BOARD.md` and its quiz in `QUIZZES.md`.** Confirm every implicit criterion is met and point to the specific code that satisfies it.
2. **Re-read your own tests.** Mentally remove the feature — would the test fail? If not, it's a false positive. Fix or delete it.
3. **Run the tests.**
   - Python: `pytest tests/unit -x -q` and, if adapters/entrypoints were touched, the relevant `tests/integration/` subset.
   - Type check: `mypy src` (must be clean for domain/application).
   - Lint: `ruff check src` if configured.
   - Frontend: `pnpm tsc --noEmit` and `pnpm lint` if scripts exist.
4. **Diff review.** Run `git diff main...HEAD` and read every changed line. Look for: debug code left in, hardcoded magic values that should live in `config.py`, missing error handling at system boundaries, inconsistent naming, forbidden imports.

Do not mark the task `✅ done` if tests fail or hexagonal boundaries are violated.

## Updating the Board

After implementation, testing, and verification are all complete:

1. **Update `BOARD.md`:** flip the task's status cell from `🔄 in progress` to `✅ done`. Leave the quiz cell as-is (`⬜` or `🔁`) — the user runs `/quiz <id>` separately.
2. **Update `CLAUDE.md`** only if:
   - A new convention was established (e.g. file naming, module structure).
   - An existing rule was clarified because of an ambiguity you hit.
   - A new cross-cutting contract was introduced (new port, new event type).
   Do not add narration of what you implemented — `CLAUDE.md` is an instruction file, not a changelog.

## Final Summary

Tell the user, in one short paragraph:

1. Task ID + title + final status.
2. Files created / modified count.
3. Tests added, which tier.
4. Anything surfaced during Verification that the user should know (deviations, follow-up work, suggested next task).
5. Next step: `/quiz <id>` to take the task quiz and flip the quiz cell.

## Critical Reminders

- If blocked by a missing dependency or unresolved question, **stop and explain** — do NOT guess or assume. Point the user at `QUESTIONS.md` if relevant.
- Prefer reading existing code and following its patterns over inventing new ones.
- When in doubt, re-read `CLAUDE.md` — it is the source of truth for architecture, and the quiz in `QUIZZES.md` is the source of truth for design intent.
- Never cross a hexagonal boundary for convenience. If the only way forward is to import a framework into `domain/` or `application/`, the design is wrong — stop and ask.
