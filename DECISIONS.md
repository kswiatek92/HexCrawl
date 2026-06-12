# HexCrawl — Decisions log

ADR-style log of non-obvious design choices. One entry per decision.

Format:
- **Context** — what problem / constraint prompted this
- **Decision** — what we chose
- **Alternatives considered** — what we rejected and why
- **Consequences** — what this costs us (the trade-off, honestly stated)

Entries are append-only. If a decision is reversed, add a new entry that supersedes the old one — don't edit history.

---

## 0006 — Game repository persists the `(Dungeon, Player)` pair

**Date:** 2026-06-12
**Status:** Accepted
**Scope:** `src/domain/ports/game_repository.py` (the port contract) and
`src/adapters/db/game_repository.py` (the adapter). Sets how a *saved run* is
written and restored, and the transaction-ownership convention every DB
repository follows (2.5 included).

### Context

Task 2.4 implements `IGameRepository`. The port originally took/returned a
`Dungeon` alone. Implementing it surfaced one gap with two faces:

1. The 2.3 schema has a 1:1 `players` table, but `save(dungeon)` is handed no
   player — so it could never be written, and a restored run would lose the
   player's HP / position.
2. `DungeonRow.user_id` is `NOT NULL` (the indexed owner column), but the
   domain `Dungeon` carries no user — so `_to_orm` couldn't even produce a
   valid row.

Both stem from the same fact: **a saved run is the dungeon *and* its player**
(and the run's owner *is* the player's user). The domain deliberately keeps
`Dungeon` and `Player` as separate objects — services take both,
`process_turn(dungeon, player, action)` (QUESTIONS.md line 41) — but that is a
statement about *domain modelling*, not about what a single checkpoint must
contain.

### Decision

1. **Widen the port to travel the pair.**
   `save(dungeon, player) -> tuple[Dungeon, Player]` and
   `get(game_id) -> tuple[Dungeon, Player] | None`. A bare tuple (not a new
   `GameState` type) keeps the domain change to one file; a named aggregate can
   come later if Phase 3 finds the pair unwieldy.
2. **`user_id` is denormalised onto `dungeons` from `player.user_id`** — no
   migration; the full 2.3 schema (`dungeons`/`players`/`floors`/`enemies`) is
   used as built.
3. **The repository does not own the transaction.** `save` does `merge` +
   `flush` (no commit); the Unit-of-Work boundary belongs to the calling use
   case / ambient `session.begin()` (Phase 3). The `AsyncSession` is itself the
   per-request UoW (quiz 2.4 Q4). The session is constructor-injected.
4. **Upsert via `session.merge`** — idempotent on `dungeon_id`; with the
   `delete-orphan` cascade from ADR-0005 it reconciles removed floors/enemies
   (verified: a re-save dropping an enemy deletes its row).

This does **not** reverse ADR/QUESTIONS line 41: the domain model and service
signatures are unchanged (`Dungeon` still has no `player` field). Only the
*persistence port* carries both.

### Alternatives considered

- **Defer the player; persist the dungeon only.** Rejected: leaves `user_id`
  unfillable (NOT NULL), leaves the `players` table permanently unwritten, and
  makes a "saved game" non-restorable (no player state). It pushed the real
  decision to Phase 3 while shipping a repo that can't actually write a row.
- **Make `dungeons.user_id` nullable, or drop it.** Rejected: needs a migration
  and *still* doesn't persist the player — it only hides the NOT-NULL symptom
  while the resume-state gap remains.
- **A separate `save_player` / player port.** Rejected: a "save game" becomes
  two calls (non-atomic unless threaded through one transaction by every
  caller) and adds port surface for no gain over carrying the pair.
- **A named `GameState(dungeon, player)` domain type now.** Deferred, not
  rejected: reasonable, but more domain surface than 2.4 needs; revisit in
  Phase 3 if tuple-passing gets noisy across use cases.

### Consequences

**Gains:**
- Saved runs are fully restorable (dungeon + player), satisfying the
  `GET /game/{id}` "fetch saved game state" surface.
- `dungeons.user_id` is populated, so the "my games" index is real — no
  migration, the 2.3 schema is used end-to-end.
- One clear transaction-ownership rule for every repo (use case commits), so
  2.5 (`PostgresScoreRepository`) follows the same shape.

**Costs:**
- The port now passes a **bare tuple**; callers unpack `dungeon, player`. If
  this spreads awkwardly through Phase 3, a named aggregate is the follow-up.
- `get` must treat a dungeon row with no player row as a **storage-integrity
  fault** (raises) — unreachable via `save`, but a real branch.
- **Enemy order within a floor is not preserved by the schema** (no order
  column on `enemies`), so a DB round trip may reorder a floor's enemies; the
  pure mapper preserves order, and equality-sensitive checks must sort by
  `enemy_id`. Flagged for task 2.6 — add an `order_by` if order proves
  semantically load-bearing.

### References

- [game_repository.py (port)](src/domain/ports/game_repository.py) — widened contract.
- [game_repository.py (adapter)](src/adapters/db/game_repository.py) — mappers + merge/flush/get.
- [ADR-0005](#0005--orm-persistence-shape-relational-aggregate-11-player-jsonb-grid-fk-free-scores) — the schema this writes to (delete-orphan cascade, selectin).
- [QUESTIONS.md line 41](QUESTIONS.md) — Dungeon/Player domain separation (unchanged by this).

---

## 0005 — ORM persistence shape: relational aggregate, 1:1 player, JSONB grid, FK-free scores

**Date:** 2026-06-10
**Status:** Accepted
**Scope:** `src/adapters/db/models.py` and the create-tables migration
(`alembic/versions/cb4012b33ce0_*`). Fixes the row layout the Phase 2.4/2.5
repositories map domain dataclasses to/from, and the loading strategy every
read of a run inherits.

### Context

Task 2.3 turns the pure domain dataclasses (`Dungeon`, `Floor`, `Enemy`,
`Player`, `Score`) into a Postgres schema. Several non-obvious mapping calls had
to be made, and a genuine tension surfaced:

1. **Persist a run as relational tables, or seed-only?** The `Dungeon` model
   (ADR/task 1.6) notes that floors are a runtime cache regenerable from
   `(seed, index)`, implying minimal persistence. But the 2.3 quiz (Q2/Q3)
   tests N+1 and `selectin` loading on `Dungeon → Floors → Enemies`, which only
   exists if floors/enemies are real tables.
2. **How does the per-run `Player` map?** (Quiz Q5 names FK vs JSONB vs table.)
3. **How is the 80×50 `Floor.tiles` grid stored** — and ground `items`?
4. **Does a `Score` reference its `Dungeon` by foreign key?**

### Decision

1. **Relational aggregate, not seed-only.** `dungeons → floors → enemies` are
   tables (1:N each), with `players` 1:1. The Postgres checkpoint therefore
   holds the *mutated* run state — current HP, pickups, `awake` flags — that a
   seed alone cannot reconstruct. Collections load with **`lazy="selectin"`**:
   one extra `... IN (:ids)` query per aggregate level, sidestepping both the
   N+1 problem and the parent-row multiplication a JOIN-based eager load causes
   on one-to-many. The seed regeneration in 1.6 remains valid for *generating*
   unseen floors; it just isn't the *persistence* mechanism.
2. **`Player` is a separate 1:1 table** (`players`) whose primary key *is* a
   `dungeon_id` FK (`ondelete=CASCADE`). Normalised and queryable, and it keeps
   the domain's deliberate Dungeon/Player separation intact in the schema.
3. **Floor grid as JSONB.** `tiles` (nested string array) and `items` (keyed by
   `"x,y"`) are `JSONB` columns; `stairs` and all `(x, y)` positions are two
   integer columns. The grid is always read/written whole, never queried
   cell-by-cell, so a blob beats a ~4000-row-per-floor cells table.
4. **`scores.dungeon_id` is a plain column, not a foreign key.** A `Score` is an
   immutable leaderboard record that must outlive its run (active runs live in
   Redis and may be GC'd; an admin path may hard-delete a dungeon). A composite
   index `(value DESC, computed_at ASC)` backs the `IScoreRepository` ordering.

ORM classes carry a `*Row` suffix and import only SQLAlchemy + `BehaviourType`
(`adapters → domain` is allowed); the enum persists as `native_enum=False`
(portable VARCHAR + CHECK, not a migration-hostile Postgres `ENUM`).

### Alternatives considered

- **Seed-only dungeon persistence** (store `seed` + `current_floor_index`,
  regenerate floors on load). Rejected: regeneration yields *initial* state, not
  the mutated state a mid-run save needs, and it leaves nothing for the 2.3
  quiz's relationship/loading questions to describe. Kept as the floor-*generation*
  path, not the persistence path.
- **`lazy="joined"` / `"subquery"`** for the collections. Rejected as the
  default: a `joined` one-to-many multiplies the parent row per child; `selectin`
  is the standard win for collections. Repos can still override per-query with
  `selectinload`/`joinedload` where a specific access pattern wants it.
- **Player embedded as a `dungeons.player` JSONB blob**, or flattened onto the
  `dungeons` row. Rejected: blob loses queryability/FK integrity; flattening
  conflates "the run" with "the player" and fights the 1.6 separation.
- **Tiles as a `tiles(floor_id, x, y, type)` table.** Rejected: thousands of
  rows per floor for data only ever handled as a whole grid — pure overhead.
- **`scores.dungeon_id` as a real FK** (with `ON DELETE SET NULL`/`RESTRICT`).
  Rejected: couples permanent leaderboard history to ephemeral run lifecycle.

### Consequences

**Gains:**
- Mid-run checkpoints round-trip exact state (HP, pickups, aggro), enabling the
  game-over / descent / explicit-save persistence points in CLAUDE.md.
- `selectin` makes loading a run a small constant number of queries regardless
  of floor/enemy count — no N+1, no row blow-up.
- Leaderboard reads and durability are decoupled from run storage; the composite
  index serves `top_n` (global) and the weekly range scan.

**Costs:**
- More tables and FKs than a seed-only design — more migration surface and more
  mapping code in 2.4 (domain ↔ ORM translation is now non-trivial). Accepted:
  it's the translation layer the hexagonal split exists to contain.
- JSONB `tiles`/`items` are opaque to SQL — can't filter/aggregate on grid
  contents in the DB. Fine for v1 (the game reasons over them in Python); a
  future "search floors containing X" feature would need a different shape.
- `selectin` issues a second round trip per collection (vs a single joined
  query). Negligible here (bounded fan-out) and the right default; pathological
  cases can opt into `joinedload` at the call site.
- A run hard-deleted from `dungeons` leaves its `scores` rows with a dangling
  `dungeon_id` (no referential guarantee). Intended — those rows are the
  leaderboard's source of truth, not a view of live runs.

### References

- [models.py](src/adapters/db/models.py) — the five `*Row` classes + composite index.
- [cb4012b33ce0](alembic/versions/cb4012b33ce0_create_game_and_score_tables.py) — create-tables migration.
- [ADR-0004](#0004--alembic-settings-sourced-url--empty-baseline-migration) — the migration workflow this is the first real payload for.
- [QUIZZES.md Task 2.3](QUIZZES.md) — N+1, loading strategies, identity map, player-mapping trade-off.
- [SQLAlchemy — relationship loading](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#select-in-loading).

---

## 0004 — Alembic: `Settings`-sourced URL + empty baseline migration

**Date:** 2026-06-02
**Status:** Accepted
**Scope:** `alembic.ini`, `alembic/env.py`, `alembic/versions/`, and
`src/adapters/db/base.py`. Sets the migration-workflow conventions for all of
Phase 2 (tasks 2.3–2.5) and every migration thereafter.

### Context

Task 2.2 stands up Alembic before any ORM models (2.3) or repositories
(2.4/2.5) exist. Two non-obvious calls had to be made to wire it up, and both
shape every later migration, so they get a durable home here:

1. **Where does the connection string come from?** Alembic's scaffold puts a
   literal `sqlalchemy.url` in `alembic.ini`. The app already has one config
   home (`src/config.Settings`, pydantic-settings, env/`.env`), and the URL is
   a credential.
2. **What does the "initial migration" contain** when there are no models to
   diff against? Autogenerate has nothing to compare `Base.metadata` to yet.

The async-engine half of the setup (`run_sync` bridge) is *not* re-litigated
here — it's the direct consequence of [ADR-0003](#0003--asyncio-end-to-end-in-adapters-and-entrypoints-sync-domain-cpu-work-to-celery)
(adapters are async, asyncpg). This ADR is only about the two calls above.

### Decision

1. **`env.py` sources the DB URL from `Settings`, not `alembic.ini`.**
   `alembic.ini`'s `sqlalchemy.url` is left blank; `env.py` calls
   `config.set_main_option("sqlalchemy.url", Settings().database_url)` at
   import. One source of truth, and no credential committed to the repo.
2. **`target_metadata = Base.metadata`**, where `Base` (with the naming
   convention — see QUESTIONS.md Phase 2) lives in `src/adapters/db/base.py`.
   Every ORM model inherits it so autogenerate sees a single `MetaData`.
   `compare_type=True` so column-type changes are detected.
3. **The initial migration is an empty baseline** (`down_revision = None`,
   `upgrade`/`downgrade` are `pass`). It establishes the root of the revision
   history against an empty database. The first *table-creating* migration is
   `--autogenerate`d in task 2.3 once ORM models exist — models drive the
   schema, never hand-written DDL racing ahead of them.

### Alternatives considered

- **Keep the URL in `alembic.ini`.** Rejected: two places to change the DB
  target, and a real credential would sit in a committed file. A blank ini +
  `Settings` injection keeps secrets in env where the rest of the app reads
  them.
- **Read `os.environ["DATABASE_URL"]` directly in `env.py`** (skip `Settings`).
  Rejected: re-implements parsing/defaults that `Settings` already owns and
  invites drift if the default ever changes. The cost — see Consequences — is
  that `Settings()` requires `JWT_SECRET`; accepted because migrations run in
  the same environment as the app, which needs it anyway.
- **Hand-write the first migration's tables now (2.2).** Rejected: with no ORM
  models, 2.3's autogenerate would then diff models against hand-authored SQL,
  inviting drift and contradicting the model-driven workflow QUIZZES.md 2.3
  assumes. Geometry-before-models is backwards for an ORM project.
- **Ship no migration at all in 2.2, defer to 2.3.** Rejected: leaves the
  board's "+ initial migration" unfulfilled and means there's no revision
  history root to autogenerate *against* — the first autogenerate would have a
  `None` base anyway, so we may as well make that root explicit and tested now.

### Consequences

**Gains:**
- Single source of truth for the DB target; no secret in version control.
- `alembic upgrade head` / `downgrade base` work today and are tested
  (single-head/single-base guards + a manual round-trip), so 2.3 builds on a
  proven base instead of debugging wiring and schema at once.
- Deterministic constraint/index names from migration one (naming convention
  on `Base.metadata`), so autogenerate diffs stay stable across environments.

**Costs:**
- **`env.py` depends on the full `Settings`**, so any online Alembic command
  (`upgrade`, `downgrade`, `check`, `current`) requires `JWT_SECRET` to be
  present — even though migrations don't use it. Dev `.env` supplies it (empty
  string passes), CI/deploy already set it. The offline `revision` command does
  not run `env.py`, so generating migrations is unaffected. If this coupling
  ever bites (e.g. a migrations-only container), the fix is a narrower
  migration-settings object — deferred until there's a concrete need.
- An empty baseline is a real revision that does nothing, which can look like a
  mistake. Mitigated by an explicit docstring in the migration file.

### References

- [base.py](src/adapters/db/base.py) — `Base` + naming convention.
- [env.py](alembic/env.py) — URL injection + async `run_sync` bridge.
- [ADR-0003](#0003--asyncio-end-to-end-in-adapters-and-entrypoints-sync-domain-cpu-work-to-celery) — the async decision this builds on.
- [QUESTIONS.md Phase 2](QUESTIONS.md) — naming-convention decision (line 83).
- [Alembic — async recipe](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).

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
