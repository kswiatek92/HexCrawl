# HexCrawl — Copilot Code Review Instructions

## Project overview

HexCrawl is a browser-based turn-based dungeon crawler (roguelike) with a global leaderboard.
The backend is built with **strict hexagonal (ports & adapters) architecture** in FastAPI.

## Architecture

Dependency direction — never violated:

```
entrypoints → application → domain ← adapters
                                   ↑
                              ports (Protocols)
```

| Layer | Path | Allowed imports |
|-------|------|-----------------|
| Domain | `src/domain/` | Pure Python stdlib only. Zero framework deps. Ever. |
| Application | `src/application/` | Domain only. No FastAPI, SQLAlchemy, Redis, Celery, Pydantic. |
| Adapters | `src/adapters/` | Domain ports + their framework (SQLAlchemy, Redis, Celery). |
| Entrypoints | `src/entrypoints/` | Application layer only. FastAPI routers. |

## Key design decisions

- **ADR-0001** — Domain enums are `StrEnum` with `value == name`. A lock test enforces this.
- **ADR-0002** — `Score` is `@dataclass(frozen=True)`. Score formula is a free function `compute_score_value`, never a method.
- **ADR-0005** — ORM collections use `lazy="selectin"`. `scores.dungeon_id` is a plain column (not FK).
- **ADR-0006** — `IGameRepository.save(dungeon, player)` takes a pair. Repositories do `merge`/`flush` only — no `commit`. Transaction boundary belongs to the calling use case. `AsyncSession` is constructor-injected.
- Game state serialisation lives in `src/application/game_state.py` — the cache adapter is a generic `str` store only.
- `SubmitScore` enqueues via `IScoreRecalcQueue` port — application layer never imports Celery. Task args are JSON-serialisable primitives (`score_id`), never domain objects.

## Review checklist

### 🔴 Blockers — must fix before merge

- Any import of FastAPI, SQLAlchemy, Redis, Celery, or Pydantic inside `src/domain/` or `src/application/`
- `IScoreRecalcQueue` bypassed — Celery task imported directly in application layer
- Serialisation logic inside the cache adapter (must live in `src/application/game_state.py`)
- Logic bugs, off-by-one errors, incorrect control flow
- Missing `await` on coroutines; unhandled async errors
- `None` dereferences that will raise at runtime
- Race conditions in async flows (Redis TTL, WebSocket lifecycle, Celery enqueue order)
- Repository calling `session.commit()` — only use cases may commit
- `IGameRepository.save()` called with only `Dungeon` — must pass `(dungeon, player)` pair
- Domain object passed as Celery task argument — must be a JSON-serialisable primitive
- `Score` mutated after creation — use `dataclasses.replace`
- Alembic migration creating a second head
- JWT secret or Supabase service role key hardcoded or logged
- Missing `get_current_user` dependency on authenticated endpoint
- Raw SQL with string interpolation

### 🟡 Warnings — should fix

- `Any` in `src/domain/` or `src/application/`
- `asyncio.run()` inside async context; blocking I/O (`time.sleep`, `requests.*`) in async path
- Missing `await` on `session.flush()` or `session.merge()`
- `lazy="select"` on collections (N+1 risk) — use `selectin`
- ORM model defined outside `src/adapters/db/`
- Domain↔ORM mapping logic crossing the port boundary
- New use case or adapter added without tests
- Integration test not using testcontainers
- `print()` — use `structlog`
- Port not named `I*Port` / `I*Repository`
- Domain enum `value != name` (violates ADR-0001)
- `compute_score_value` moved into a class method (violates ADR-0002)
- Commit not following Conventional Commits (`feat:`, `fix:`, `chore:`)

### 🔵 Suggestions — optional

- Magic numbers without named constants (e.g. raw `7200` instead of `GAME_STATE_TTL_SECONDS`)
- Missing docstring on exported port interfaces
- Test names not following `test_<what>_when_<condition>_<expected_outcome>`
- `if/elif` chain for action dispatching that could use a `match` statement (Python 3.12)

## Review format

For every issue leave an inline comment:

```
🔴 BLOCKER | 🟡 WARNING | 🔵 SUGGESTION — <one-line title>

<direct explanation — no filler phrases>

**Suggested fix:**
<concrete code or description>
```

End with a summary comment on the PR:

```
## Review Summary
**Verdict:** ✅ APPROVED | ⚠️ APPROVED WITH COMMENTS | 🚫 CHANGES REQUIRED
**Blockers:** N  **Warnings:** N  **Suggestions:** N

### Critical issues
- `path/to/file.py:42` — <title>

### Overall assessment
<2–4 sentences>
```

`REQUEST_CHANGES` if any blocker. One blocker = no merge.
