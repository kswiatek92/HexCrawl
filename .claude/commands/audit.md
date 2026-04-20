You are performing a comprehensive source code audit of this project. Your output will be used by a future AI agent to fix problems, so be **specific and actionable** — include file paths, line numbers, code snippets, and concrete fix descriptions.

## Pre-flight

1. Read `CLAUDE.md` for project conventions, stack, and architectural rules.
2. Read `BOARD.md` for current project status and in-flight work.
3. Discover the full project structure: `src/domain/`, `src/application/`, `src/adapters/`, `src/entrypoints/`, `tests/`, `alembic/`, frontend sources, Docker/infra files, requirements files.

If there is no application source code yet (only scaffolding), say so and stop.

## Audit Dimensions

Run each dimension as a parallel investigation. For every finding, assign a severity: **CRITICAL** (breaks correctness/security), **WARNING** (likely to cause problems), or **INFO** (improvement opportunity).

### 1. Hexagonal Architecture Boundary Violations

This is the highest-priority dimension for this project — the backend is the portfolio centrepiece and its value depends on strict layering.

- **Domain purity**: grep `src/domain/` for any import of `fastapi`, `sqlalchemy`, `redis`, `celery`, `pydantic` (except `BaseModel`-free usage is ok — domain uses dataclasses), `asyncpg`, `supabase`. Every such import is CRITICAL.
- **Application purity**: `src/application/` must depend only on `domain/` and `domain/ports/` — never on concrete adapters. Flag any import from `src/adapters/` or `src/entrypoints/`.
- **Port definition location**: all `Protocol` interfaces must live in `src/domain/ports/`. Flag protocols defined in adapters or application.
- **Adapter leakage**: `src/entrypoints/` should depend on application use cases, not instantiate adapters inline (use DI). Flag direct `SessionLocal()` / `redis.Redis()` construction in routers.
- **Dependency direction**: verify `entrypoints → application → domain ← adapters`. Any arrow pointing the wrong way is CRITICAL.
- **Pydantic in domain**: domain models must be plain dataclasses, not Pydantic models. Pydantic belongs in `entrypoints/` schemas.

### 2. Bugs & Correctness

- Logic errors, off-by-one, null/None handling, race conditions (especially around the WebSocket turn loop).
- **Turn loop integrity**: verify `process_turn` validates action → runs enemy AI → updates state → persists — in that order, atomically. Flag any path where state is pushed to the client before persistence.
- **Redis TTL**: active game state uses TTL 2h per `CLAUDE.md`. Flag missing `EXPIRE` / inconsistent TTLs.
- **Checkpoint persistence**: state must persist to Postgres on game over, floor descent, and explicit save (per `CLAUDE.md`). Flag missing checkpoints.
- **Score calculation**: `floors reached × enemies killed × item multiplier`. Verify this formula is implemented exactly once (not duplicated) and matches the spec.
- **Weekly reset**: Celery Beat Mon 00:00 UTC. Flag wrong timezone, wrong day, or non-idempotent reset.
- Missing error handling at system boundaries (DB queries, Redis calls, Supabase Auth JWT verification, Celery task failures).
- Async correctness: `await` missing on async calls, blocking I/O inside async functions, sync SQLAlchemy session used in async context.
- `Any` leaks in domain or application layers (forbidden by `CLAUDE.md` conventions).

### 3. Security

- OWASP Top 10: XSS in the React frontend, injection via raw SQL in adapters, broken auth, sensitive data exposure, CSRF on mutating HTTP endpoints.
- **JWT validation**: every authenticated HTTP route and the WebSocket handshake must validate the Supabase JWT. Flag unguarded endpoints.
- **WebSocket auth**: `/ws/game/{session_id}` must verify the JWT on connect AND verify the authenticated user owns `session_id`. Flag either gap.
- **Session ownership**: `GET /game/{id}`, `POST /game/{id}/abandon`, and all score-affecting routes must verify the caller owns the game/score row.
- **Leaderboard write path**: scores should only be writable by the server (never directly by the client). Flag any client-submitted score that isn't reconstructed from server-side game state.
- Raw SQL with string interpolation (use SQLAlchemy parameters / `text()` bindparams).
- Secrets committed: check for real values in `.env`, hardcoded JWT secrets, Supabase service-role keys in client-reachable code.
- CORS config: verify allowed origins are not `*` in production config.

### 4. Overengineering

- Abstractions used only once (unnecessary wrappers, factories, strategy patterns for single implementations).
- Premature generalization: config-driven behavior where hardcoding is fine for MVP.
- Ports with a single adapter and no plausible second implementation — flag only if the port adds indirection without testability benefit.
- Deep inheritance hierarchies where composition or a flat approach works.
- Unnecessary indirection (use case → service → service → repo where use case → repo suffices).
- Feature flags, backwards-compatibility shims, dead code paths.
- Over-abstracted generics or Protocol hierarchies.
- Files that can be deleted entirely with no impact.
- Utility functions used in only one place — should be inlined.

### 5. Test Coverage & Quality

- List all test files found and what they cover, grouped by `tests/unit/domain/`, `tests/unit/application/`, `tests/integration/adapters/`, `tests/integration/entrypoints/`, `tests/e2e/ws/`.
- Identify source files/functions with **no test coverage**, weighted by layer importance (domain > application > adapters > entrypoints).
- **Domain tests must be instant (< 1s) and do no I/O** per `CLAUDE.md`. Flag any domain test that imports a real DB/Redis/Celery or uses `AsyncMock` of an infrastructure client.
- **Application tests should use fake ports, not mocks of concrete adapters.** Flag uses of `unittest.mock` against SQLAlchemy sessions or Redis clients in application tests.
- Check test quality:
  - Do tests assert meaningful behavior or just "doesn't throw"?
  - Are turn-loop edge cases covered (invalid action, dead player, full inventory, stair descent at boss kill)?
  - Is the BSP dungeon generator tested for determinism given a seed?
  - Is the score formula tested with boundary inputs (0 enemies, 0 floors, max multiplier)?
  - Is the weekly-reset Celery task tested for idempotency?
  - Is WebSocket auth failure tested (bad JWT, wrong owner)?
- Flag tests that are:
  - Testing implementation details instead of behavior
  - Overly mocked (mocking the thing being tested)
  - Duplicating other tests
  - Flaky (timing-dependent, order-dependent, relying on wall-clock)

### 6. Extensibility & Maintainability

- **Action dispatch**: per `CLAUDE.md` conventions, turn actions should use Python 3.12 `match` statements. Flag if/elif chains on action type.
- **Port surface**: are ports coarse enough that adapters aren't leaky, and fine enough that tests can fake them cheaply?
- **Enemy AI**: is behaviour (melee / ranged / boss) dispatched via a clean interface or hardcoded switch scattered across the codebase?
- **Dungeon generator**: is the BSP algorithm isolated behind a `DungeonGenerator` service so alternate generators can be swapped in?
- **Database schema**: missing indexes on hot paths (`leaderboard` by score desc, `game_state` by `session_id`, `score` by `user_id, created_at`), missing foreign keys, denormalization that will cause problems.
- **API consistency**: endpoints consistent in error format (`{detail: ...}` FastAPI default vs custom envelope), response shape, auth dependency injection style.
- **Frontend canvas rendering**: is the render loop decoupled from the turn loop, or tangled? Is game state held in React state vs a ref / external store?
- **Magic strings/numbers**: hardcoded values (floor count, HP, damage, TTL seconds, leaderboard page size) that should be constants in `config.py` or domain constants.
- **Config loading**: is every env var accessed through `config.py` Pydantic Settings, or are there `os.getenv` calls scattered in adapters?

### 7. Consistency with Documented Contracts

- Cross-reference implemented HTTP routes against the API surface table in `CLAUDE.md`. Flag missing routes and undocumented extra routes.
- Cross-reference implemented Celery tasks against the task table in `CLAUDE.md` (`score_recalc`, `map_generation`, `weekly_leaderboard`). Flag missing or extra.
- Verify the folder layout matches the diagram in `CLAUDE.md`. Flag misplaced modules (e.g. a SQLAlchemy model inside `domain/`).
- Verify commit prefixes (`feat/`, `fix/`, `chore/`) and Conventional Commits on recent history — INFO only.

## Output Format

Structure your output as a markdown report with this exact structure:

```
# Code Audit Report — [date]

## Summary
- Total findings: X (Y critical, Z warnings, W info)
- Files audited: N
- Architecture boundary violations: N
- Test coverage assessment: [brief]

## Critical Findings
[List each with: file:line, description, suggested fix]

## Warnings
[List each with: file:line, description, suggested fix]

## Info / Improvements
[List each with: file:line, description, suggested fix]

## Architecture Boundary Violations
[Table: file | forbidden import | target layer | fix]

## Test Coverage Gaps
[Table: source file | layer | tested? | missing coverage areas]

## API & Task Contract Coverage
[Table: contract item (route / celery task) | status (implemented/partial/missing) | notes]

## Recommendations
[Prioritized list of what to fix first]
```

Every finding MUST include:
- Exact file path and line number(s)
- A code snippet showing the problem (if applicable)
- A concrete description of what to change (not vague "improve this")

## Cross-Check Rule

For every finding that references a convention or architectural decision, cite the specific section of `CLAUDE.md` (e.g. "Architecture — Hexagonal / Ports & Adapters", "Code conventions", "WebSocket turn loop") that supports it. Do not paraphrase from memory — re-read the file and copy the relevant text.

For every finding that references an in-flight task or known status, cite the line from `BOARD.md`.

If you cannot find a supporting passage for a claim, do not make the claim.

Do NOT include:
- Style/formatting opinions (that's for linters — `ruff`, `black`, `mypy`, `eslint`)
- Suggestions to add comments or documentation to code you didn't flag for other reasons
- Generic best-practice advice not tied to specific code in this repo
- Claims about architectural rules that you cannot back with a direct quote from `CLAUDE.md`
