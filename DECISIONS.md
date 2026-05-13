# HexCrawl — Decisions log

ADR-style log of non-obvious design choices. One entry per decision.

Format:
- **Context** — what problem / constraint prompted this
- **Decision** — what we chose
- **Alternatives considered** — what we rejected and why
- **Consequences** — what this costs us (the trade-off, honestly stated)

Entries are append-only. If a decision is reversed, add a new entry that supersedes the old one — don't edit history.

---

## 0003 — `asyncio` end-to-end in adapters and entrypoints; sync domain; CPU work to Celery

**Date:** 2026-05-13
**Status:** Accepted
**Scope:** All of `src/adapters/` and `src/entrypoints/` (FastAPI routers, WebSocket
handlers, SQLAlchemy/`asyncpg` repos, `redis.asyncio` cache). Domain (`src/domain/`)
and most of `src/application/` stay synchronous. Heavy CPU work is delegated to Celery
(`src/adapters/tasks/`) rather than awaited on the event loop.

### Context

HexCrawl's defining workload is the **WebSocket turn loop** (`/ws/game/{session_id}`):
many long-lived connections, each mostly idle waiting for the player's next action,
each turn touching Redis (active state) and occasionally Postgres (checkpoint /
game-over). The leaderboard and REST surface are also I/O-bound network calls.

The naive "async makes Python fast" framing is wrong and worth pinning down before
the project grows: async helps when work is **waiting on I/O**, not when it's
**burning CPU**. HexCrawl has both — turn resolution and BSP map generation are
CPU-bound — so the model needs to be explicit about where async lives and where it
doesn't, otherwise the boundary will rot the first time someone slaps `async def`
on a pure function "for consistency."

This is also a hexagonal-boundary concern: if the domain becomes `async`,
domain tests need an event loop, and the framework-agnostic property the project is
built around weakens.

### Decision

1. **Adapters and entrypoints are async all the way down.**
   - FastAPI routers use `async def`.
   - DB access via SQLAlchemy 2.x async engine + `asyncpg`.
   - Cache access via `redis.asyncio`.
   - WebSocket handlers `await` per-message; one event loop holds N sessions.
2. **Domain stays synchronous.** `src/domain/services/` and `src/domain/models/`
   are plain sync functions and dataclasses. No `async def`, no `await`, no
   `asyncio` import. This is enforced socially via review and `/audit`.
3. **Application use cases are async only where they fan out to async ports.**
   A use case that calls `await cache.get(...)` is `async def`; one that only
   composes domain services stays sync. No blanket "everything async."
4. **CPU-bound work goes to Celery, not the event loop.**
   - Deep-floor BSP generation → `map_generation` task.
   - Score recalculation → `score_recalc` task.
   - Weekly leaderboard reset → Celery Beat.
   Shallow per-turn CPU (enemy AI, action resolution) runs inline because it's
   fast enough that yielding would cost more than it saves; if profiling ever
   shows a turn blocking the loop > ~5 ms, that becomes a Celery candidate too.
5. **No `asyncio.run()` inside request handlers, no `run_in_executor` shortcuts
   in the domain.** If something needs to escape the loop, it goes to Celery.

### Alternatives considered

- **Sync FastAPI + threadpool everywhere.** FastAPI supports `def` routes via a
  threadpool, and SQLAlchemy has a mature sync API. Rejected: WebSocket fan-out
  is the killer use case, and ~8 MB of stack per idle player doesn't scale to the
  "thousands of concurrent sessions" the portfolio story rests on. Threads also
  make the WebSocket lifecycle (cancellation, broadcast) much harder than
  `asyncio.TaskGroup`.
- **Async everywhere, domain included.** Rejected: it would force every domain
  unit test through `pytest-asyncio` for no I/O reason, colour pure functions,
  and weaken the hexagonal boundary (an `async def` domain method effectively
  imports the asyncio runtime as a dependency). Domain tests should stay
  instant and framework-free.
- **Trio / AnyIO as the runtime.** Rejected for now: ecosystem mismatch
  (`asyncpg`, `redis.asyncio`, Celery, FastAPI all assume asyncio); the
  structured-concurrency wins from Trio are partly available via
  `asyncio.TaskGroup` in 3.11+. Worth revisiting only if cancellation
  semantics around WebSockets become painful.
- **Run BSP / score recalc inline with `asyncio.to_thread`.** Rejected as the
  default: it sidesteps the event loop block but still consumes a worker
  process's threadpool slot and gives no retry / scheduling / visibility.
  Celery gives durable queues, retries, and Beat scheduling — which the project
  needs anyway for the weekly leaderboard.
- **Skip Celery, do everything inline.** Rejected: weekly leaderboard reset and
  async score recalc are explicit features in CLAUDE.md, and the portfolio
  value of demonstrating a worker tier is real.

### Consequences

**Gains:**
- One process can hold thousands of idle WebSocket sessions; per-coroutine
  memory is ~KB instead of ~MB per thread.
- Per-turn Redis + Postgres I/O overlaps cleanly; no thread-pool tuning.
- Domain stays instant-to-test and framework-free — the hexagonal boundary
  is reinforced by the sync/async split, not just by import discipline.
- Celery handoff is the obvious place for CPU work, retries, and scheduling;
  the boundary is easy to explain in the portfolio writeup.

**Costs:**
- **Function colouring.** Sync domain code can't directly call async ports; the
  application layer is the only place the two worlds meet. Mostly a feature
  (it forces the use-case boundary to be explicit) but occasionally awkward.
- **Async debugging is harder.** Stack traces span tasks; deadlocks from
  forgotten `await` or blocking calls inside `async def` are easy to write and
  hard to spot. Mitigation: lint for blocking I/O in async contexts; never call
  sync DB/Redis clients from `async def`.
- **CPU-on-loop hazard.** A long-running sync call inside an `async def`
  silently freezes every other session on that worker. The "shallow CPU stays
  inline, deep CPU goes to Celery" rule depends on profiling, not vibes —
  needs a budget (~5 ms per turn) once we can measure.
- **Test ergonomics split.** Adapter and entrypoint tests need
  `pytest-asyncio`; domain tests don't. Acceptable, but new contributors will
  hit the seam.
- **Two runtimes to operate** (uvicorn + Celery worker + Beat). Already in
  the local-dev setup, but it's three terminals instead of one.

### References

- [CLAUDE.md — "Async all the way down" rule](CLAUDE.md) — the conventions
  section this entry pins down precisely.
- [SQLAlchemy async ORM](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [`redis.asyncio`](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Celery — Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)

---

## 0002 — `Score` formula and frozen dataclass

**Date:** 2026-04-27
**Status:** Accepted
**Scope:** `src/domain/models/score.py` (`Score`, `compute_score_value`,
`DAMAGE_PENALTY_WEIGHT`); also fixes the conventions for any future
`ScoreService.compute()` (task 1.18) and `SubmitScore` (task 3.3) work.

### Context

`QUESTIONS.md` Task 1.7 had pinned the high-level scoring direction —
weighted-on-floors formula, damage-taken penalty only, ≥ 5 kills threshold
enforced *outside* `ScoreService` — but explicitly deferred three tactical
choices to "during 1.7 / 1.18 implementation":

1. Exact exponent on the floors term (`floors_reached²` was suggested but
   not locked).
2. Exact damage-penalty math (subtractive vs multiplicative falloff).
3. Whether `Score` should be mutable like the other domain models or
   frozen as a snapshot.

These pin down the wire shape of every leaderboard entry the project will
ever produce, so they need a durable home.

### Decision

1. **Formula:**

   ```
   value = max(0, floors_reached**2 * kills * item_multiplier
                  - damage_taken * DAMAGE_PENALTY_WEIGHT)
   ```

   `DAMAGE_PENALTY_WEIGHT = 1` for v1. Float intermediate is truncated to
   `int` at return so the leaderboard sorts on a stable integer type.
2. **Damage penalty: subtractive**, not multiplicative. The `max(0, ...)`
   clamp also serves as the zero-score guard QUIZZES.md Task 1.7 Q1 calls
   out (multiplicative-zero on any axis already yields 0; the clamp covers
   the negative case).
3. **`Score` is `@dataclass(frozen=True)`** — first frozen dataclass in
   the codebase. A score is computed once at game over and never mutated;
   freezing turns the snapshot semantic into a runtime guarantee.
4. **Formula lives as a module-level pure function** (`compute_score_value`)
   next to the dataclass — *not* a `Score` method, *not* on `ScoreService`.
   1.18's `ScoreService.compute()` will compose primitive extraction
   (Dungeon + Player → primitives) with this function.

### Alternatives considered

- **Linear floors term** (`floors_reached × kills × item_multiplier`).
  Rejected: gives no incentive to descend over grinding floor 1.
- **Higher exponent** (`floors_reached³` / exponential). Rejected: floor
  100 would dominate so hard that the rest of the formula barely matters,
  killing the multiplier and kill-count signals.
- **Multiplicative damage falloff**
  (`base × max(0, 1 - damage_taken / baseline_hp)`). Rejected: needs a
  baseline-HP constant that doesn't generalise across enemy/floor scaling,
  and creates large swings (one tank hit can ~halve a long run's score).
  Subtractive is predictable and tunable via a single weight constant.
- **Skip damage penalty entirely in 1.7, add in 1.18.** Rejected:
  `damage_taken` already lives on `Score` (one of the four input fields);
  having `compute_score_value` ignore one of its parameters in v1 would
  invite drift between the dataclass shape and the formula.
- **Score as a method on the dataclass** (`Score.from_run(...)`).
  Rejected: pulls the formula off the pure-function path and complicates
  testing in 1.19. A free function tests in isolation.
- **Mutable `Score`.** Rejected: there is no use case where a finalised
  score should change. Mutability would also weaken the "pure function"
  contract QUIZZES Task 1.7 Q3 hinges on.

### Consequences

**Gains:**
- Predictable score progression: doubling floors quadruples the score
  ceiling at fixed kills+multiplier — clear depth incentive.
- Anti-cheat is easier with subtractive math: per-axis caps in
  `ScoreService` (1.18) compose linearly with the formula.
- Frozen `Score` means `cache.set(score)` and DB writes can't be
  silently corrupted by a stray reassignment downstream.
- The pure free function is the entire formula — 1.18's `ScoreService`
  reduces to "extract primitives, call the function, build a `Score`".

**Costs:**
- Tuning the formula now requires bumping the v1 constants and
  invalidating leaderboards. The `DAMAGE_PENALTY_WEIGHT == 1` test lock
  forces the change to be conscious.
- Frozen dataclass means anywhere a `Score` needs to "update" (e.g.
  recompute after a rule change) must build a new instance via
  `dataclasses.replace`. Tolerable — recomputes are rare and async.
- `int(base - penalty)` truncates toward zero, so `1.99` → `1`. Documented
  in the function docstring; matters at the boundary between micro-scores
  but not at leaderboard scale.

### References

- [score.py](src/domain/models/score.py) — canonical implementation.
- [QUESTIONS.md task 1.7](QUESTIONS.md#L43-L46) — earlier tactical pins.
- [QUIZZES.md task 1.7 Q1/Q3/Q4](QUIZZES.md#L75-L82) — design intent the
  formula choices align with.

---

## 0001 — Domain enums use `StrEnum` with `value == name`

**Date:** 2026-04-22
**Status:** Accepted
**Scope:** All enums in `src/domain/` — currently `BehaviourType`, `ItemType`, `TileType`.

### Context

Domain enums need to:
1. Serialise cleanly to JSON for the WebSocket turn loop and REST responses (consumed by the React frontend).
2. Be readable in logs, stack traces, and debugger output.
3. Pattern-match safely in `match` statements (exhaustiveness-checkable by mypy/pyright).
4. Survive refactors without breaking scattered string literals.

### Decision

All domain enums inherit from `StrEnum` (Python 3.11+). Variant values mirror their names exactly, e.g. `WALL = "WALL"`. A test locks this invariant: `variant.value == variant.name` for every member.

### Alternatives considered

- **Plain `Enum`** — requires a custom `JSONEncoder` or per-site `.value` extraction for serialisation. Rejected: serialisation should Just Work.
- **`IntEnum`** — serialises to integers, forcing a frontend lookup table (`1 → "WALL"`) and making logs opaque. Rejected: integer values carry no external meaning for domain concepts, and debuggability matters.
- **`StrEnum` with `auto()`** — produces lowercase names (`"wall"`) as values, so value ≠ name. Rejected: breaks the "wire format matches the Python identifier" property that makes the frontend's `case "WALL":` branches obvious.
- **Tagged union / discriminated `dict` payloads** — more expressive but overkill for simple category enums; reserved for cases like `Action` (task 1.9) where variants carry different fields.

### Consequences

**Gains:**
- `json.dumps(TileType.WALL)` produces `'"WALL"'` directly — no custom encoder.
- Singletons give `is`-comparison that's typo-proof at import time (`TileType.WALLL` is a NameError; `"WALLL"` would fail silently forever).
- mypy/pyright can check `match tile:` exhaustiveness.
- Rename-safe — `TileType.WALL → TileType.SOLID_WALL` propagates via IDE refactor; string literals wouldn't.
- ~20 KB per 50×50 tile grid (2500 pointers to shared singletons), not 2500 × string-size.

**Costs:**
- Every enum variant addition forces updates to exhaustive consumer maps (e.g. `ScoreService`'s per-type weight map, the frontend sprite map, `GameService`'s passability rule). The lock-test `test_<enum>_members` will fail when members change — this is a *feature* (forces conscious update) but adds ritual to every addition.
- `StrEnum` members compare equal to their string values (`TileType.WALL == "WALL"` is `True`), which blurs the "always use the enum, never the literal" discipline. Mitigated by style: code should still compare `tile is TileType.WALL` when possible.

### References

- [tile_type.py:1-22](src/domain/models/tile_type.py#L1-L22) — canonical example.
- [QUIZZES.md Task 1.8](QUIZZES.md#L85-L91) — covers the design reasoning (retry passed 2026-04-22).
- Python docs: [PEP 663 / `enum.StrEnum`](https://docs.python.org/3/library/enum.html#enum.StrEnum).

---

*Add new decisions above this line, most recent first. Each gets a sequence number (`0002`, `0003`, …).*
