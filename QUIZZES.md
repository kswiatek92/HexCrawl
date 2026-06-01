# HexCrawl — Quizzes

**How to use**: Tell Claude `"Quiz me on HexCrawl task 1.3"` or `"Quiz me on HexCrawl Phase 1"`.
Claude will ask questions from this file one by one, grade each answer in real time, and finish with
a full profile assessment: overall score, strong areas, weak spots, and specific things to revisit.

**What these quizzes are for**: HexCrawl is a *vehicle* for becoming a stronger senior backend
engineer — not a gamedev project. Every question below is anchored in the real HexCrawl code but
drills a transferable, interview-grade fundamental: the Python object model and concurrency, data
structures and complexity, database internals (indexes, query plans, isolation, MVCC, pooling),
system-design and architecture patterns, REST/HTTP semantics, FastAPI internals, testing discipline,
and cloud-native/DevOps. The game mechanics (dungeon generation, enemy AI, pixel rendering) are
deliberately reduced to whatever *engineering* lesson they carry, and nothing more.

**Pass threshold**: 90% per quiz. In practice a 10-question quiz allows one miss (9/10); any quiz
shorter than 10 questions requires every answer correct. Some game-flavoured tasks are intentionally
short (2–4 questions) because there is little senior signal to extract from them — that is by design.

**Find-the-bug questions**: many questions present a short, *buggy* code snippet and ask you to spot
the defect. You only need to **identify** the bug in words — you never have to write or rewrite code
(this quiz is meant to be takeable from a phone or terminal). If you miss it, the grader will **not**
reveal the bug — it stays open so you can re-attempt later; ask explicitly if you want the answer.

> Note: the Phase 1 task quizzes (1.1–1.19) were rewritten away from game trivia toward these
> fundamentals. If `BOARD.md` still shows them as 🏆 passed, treat that as stale — the material is new
> and worth re-taking.

---

## Phase 1 — Domain core

---

### Task 1.1 — Repo structure

1. State the **Dependency Rule** (Clean Architecture) in one sentence, then explain how `entrypoints → application → domain ← adapters` is that same rule drawn for this repo. Which arrow does `from sqlalchemy import select` inside `domain/` violate?
2. Hexagonal calls them *ports* and *adapters*; map each of `domain/ports/`, `adapters/db/`, and `entrypoints/http/` onto the **driving (primary)** vs **driven (secondary)** adapter distinction, and say which side initiates a call.
3. The Dependency Inversion Principle (the "D" in SOLID) says high-level modules must not depend on low-level ones. How does *defining* `IGameRepository` in `domain/ports/` (not in `adapters/db/`) realise DIP at the level of source-code import direction?
4. Today the boundary is enforced "socially via review + `/audit`." Why is an `import-linter` contract a strictly stronger guarantee, and what class of regression does the automated check catch that a human reviewer routinely misses?
5. A teammate wants to collapse `domain/` and `application/` "to cut boilerplate." Explain what the application layer is *for* (use-case orchestration of ports) and name one concrete capability you lose by folding it into the domain services.

---

### Task 1.2 — `Player` dataclass

1. `@dataclass` generates `__init__`, `__repr__`, `__eq__`. Explain how `eq=True` interacts with `__hash__`: why does a default (mutable) dataclass become **unhashable**, and what two flags restore hashability?
2. `field(default_factory=list)` vs `field(default=[])` — explain the mutable-default gotcha in terms of *when* the default is evaluated (`def`-time, once) and the concrete bug a shared list causes across `Player` instances.
3. What does `@dataclass(slots=True)` change about attribute storage (`__slots__` vs `__dict__`)? Give the two trade-offs — what you gain (memory, attribute-access speed) and what you lose (dynamic attributes, some multiple-inheritance cases).
4. In DDD terms, is `Player` an **Entity** or a **Value Object**? Justify with the identity-vs-value distinction, and explain why that answer drives whether `frozen=True` is appropriate.
5. Type hints are not enforced at runtime. If `Player.hp` is annotated `int` but an adapter constructs it with `"50"`, where in this architecture should that be caught, and which tool catches it before the code ever runs?

---

### Task 1.3 — `Enemy` dataclass + `BehaviourType` enum

1. Compare `class BehaviourType(str, Enum)`, `enum.StrEnum` (3.11+), and a plain `Enum`. What does mixing in `str` buy you for JSON serialisation, and what surprising `==`/`in` behaviour does it introduce?
2. Enum members are singletons. Explain why `enemy.behaviour is BehaviourType.MELEE` is both correct and cheaper than `== "melee"`, and tie it to the general rule: use `is` only for singletons, `==` for value equality.
3. `if enemy.behaviour == "melee":` silently *works* for a `str`-mixed enum but silently *fails* (returns `False`) for a plain `Enum`. Why is "works for one enum type, fails for another" itself the argument against comparing enums to raw strings anywhere in the codebase?
4. What does `enum.auto()` produce, and when do **explicit** values matter — e.g. when the value is persisted to a DB column or sent over the wire — versus when `auto()` is safe?
5. Dispatching on `BehaviourType`: `match`, a dict-of-handlers, or polymorphism? Relate your choice to the **Open/Closed Principle** — which lets you add a new behaviour *without editing* existing dispatch code?

---

### Task 1.4 — `Item` dataclass + `ItemType` enum

1. `Item.effect: int` means damage for weapons but HP for potions — a field whose meaning depends on another field. Name the design smell, and show how a tagged union / per-type subclass makes the illegal combinations **unrepresentable**.
2. Adding a new `ItemType`: which files *must* change and which must *not* if the design respects Open/Closed? What does Fowler's "shotgun surgery" smell look like if it's done wrong?
3. The domain `Item` dataclass vs a future `ItemORM`: give two concrete problems that arise from collapsing them into one class (persistence concerns leaking into the domain; tests dragging in a DB).
4. "Tell, don't ask": contrast `if item.type == SWORD: player.hp -= item.effect` against an effect-application design. Which one keeps item rules from leaking into `GameService`, and why?
5. Should `Item` be `frozen=True`? Argue it as a **Value Object** (equality by value, no identity, safely shareable) and name what breaks if mutable items are shared across two inventories.

---

### Task 1.5 — `Floor` model

1. `tiles: list[list[TileType]]` — what is the Big-O of random access `tiles[r][c]`, and how does a list-of-lists differ from a flat `list` + `r*width + c` indexing in terms of memory layout and cache locality?
2. A 50×50 grid of enum members: explain why this is **2500 references to ~4 singleton objects**, not 2500 distinct objects, and why that makes the memory cost a non-issue.
3. `Floor` is generated once then read-only during play. What does "immutable after construction" let you safely assume about sharing/caching/thread-safety, and would you enforce it with `frozen=True`?
4. Who owns mutation of `Floor.enemies` — the `Floor`, `GameService`, or `EnemyAI`? Answer using Single Responsibility and the "anemic domain model" debate.
5. To assert "every floor has at least one **reachable** staircase," which graph-traversal algorithm verifies reachability from the spawn tile, and what is its complexity on a W×H grid?

---

### Task 1.6 — `Dungeon` model

1. In DDD, is `Dungeon` an **Aggregate Root**? Explain what invariants an aggregate root guards and why external code shouldn't reach in and mutate a `Floor` directly.
2. Storing `seed: int` instead of the generated floors trades space for compute and buys **reproducibility**. State that property precisely (same seed + same generator version ⇒ identical floors) and one way an innocuous code change silently breaks it.
3. `current_floor_index: int` vs holding a direct `Floor` reference: discuss the aliasing/serialisation trade-off — why does an index sidestep duplicate-object problems when you save and reload a run?
4. A `status` field (`IN_PROGRESS` / `COMPLETED` / `ABANDONED`) turns `Dungeon` into a small **state machine**. Which transitions should the model reject, and why is enforcing them in the domain better than in the API layer?
5. The board chose "no `player` field — Option B." What coupling does keeping `Player` out of `Dungeon` avoid, and what is the cost you pay for that decision?

---

### Task 1.7 — `Score` dataclass + scoring formula

1. Is `ScoreService.compute(dungeon) -> Score` a **pure function**? Define purity (deterministic + no side effects) and check `compute` against both clauses.
2. `Score.computed_at: datetime` — why is calling `datetime.now()` *inside* `compute` a purity violation, and how does **injecting a clock** (`now: Callable[[], datetime]`) restore testability? Tie this to dependency inversion.
3. The formula is multiplicative (`floors² × kills × multiplier`). What's the failure mode when any factor is `0`, and how would you redesign it (guarded / additive floor) so one zero doesn't annihilate a good run?
4. Python `int` is arbitrary-precision, so there's no overflow — but name a real downstream consequence of an unbounded integer when this score is serialised to JSON and read by the React client (hint: JS `Number` and 2^53).
5. Anti-cheat: should "a score from an `ABANDONED` run = 0" live in the domain `ScoreService` or the `SubmitScore` use case? Justify with the split "domain owns invariants, use case owns orchestration."

---

### Task 1.8 — `TileType` enum

1. A plain `Enum` isn't JSON-serialisable by default. What does `TileType` serialise to as a `StrEnum` vs an `IntEnum`, and which gives the React client a stable, debuggable contract (`"WALL"` vs `3`)?
2. The "is this tile passable?" rule depends on tile state (an open door). Should that predicate be a method on `TileType`, a function in `Floor`, or in `GameService`? Use the heuristic "behaviour belongs with its data, cross-entity rules belong in the service."
3. `IntEnum` members compare equal to bare ints (`TileType.WALL == 3`). Name one bug this can silently mask, and why a `StrEnum` (or plain `Enum`) is safer for a value that is mostly a label.
4. Adding `TRAP`/`WATER` without breaking existing code: what makes enum extension backward-compatible on the Python side, and what must the *frontend* and any *persisted* data handle for forward-compatibility?

---

### Task 1.9 — `Action` type union

1. `Action = Move | Attack | UseItem | ...` (a union of frozen dataclasses) vs a base-class hierarchy: give one advantage of each (`match`-driven exhaustiveness vs shared inherited behaviour).
2. This `match` on an `Action` union compiles fine but routes almost every action to the wrong handler:
   ```python
   match action:
       case Move():
           return apply_move(state, action.direction)
       case Attack:
           return apply_attack(state, action.target)
       case _:
           return state
   ```
   Find the bug and name the runtime symptom it produces.
3. "Parse, don't validate": the WebSocket delivers raw JSON. Which layer turns `{"action":"move",...}` into a typed `Action`, and why must `GameService` never receive a bare `dict`? (Anti-corruption / boundary argument.)
4. `Direction` as an enum vs a raw `(dx, dy)` tuple: what does the enum buy you for exhaustiveness, validation, and serialisation?
5. `GameService` receives an unrecognised action variant. Is that a domain error, a validation error, or a programming error — and what response (or exception) maps to each?

---

### Task 1.10 — `IGameRepository` Protocol

1. `typing.Protocol` (structural) vs `ABC` (nominal): explain "duck typing checked statically," and why ports-as-Protocols let an adapter satisfy the interface **without importing the domain** — preserving the dependency direction.
2. `get(id) -> Dungeon | None`: why return `None` rather than raise on "not found"? When is absence an expected outcome (return `None`) vs an exceptional one (raise)?
3. `@runtime_checkable`: what does it add, what does it *not* verify (method signatures), and why is that a footgun if you lean on `isinstance` for correctness?
4. The Repository pattern (Fowler/PoEAA): what illusion does it give the domain, and why is "swap Postgres for Mongo without touching the domain" the real test of whether the port leaks persistence concerns?
5. Adding `list_for_user(user_id, limit, cursor)`: does putting it on `IGameRepository` respect or violate **Interface Segregation**? When would you split a read-port from a write-port (CQRS-lite)?

---

### Task 1.11 — `IScoreRepository` Protocol

1. `top_n(n, period: str)` — enumerate the problems with `period: str` (stringly-typed, no exhaustiveness, accepts garbage) and improve the signature with an enum or `Literal`.
2. State the **Liskov Substitution Principle** precisely, then give a concrete way a `PostgresScoreRepository` could violate it while still "implementing" the Protocol (e.g. narrowing accepted inputs, or raising where the contract promised `None`).
3. Why must `top_n` return `list[Score]` (domain model) rather than `list[dict]`? What does the typed return enforce about the adapter→domain mapping boundary?
4. Should `delete(score_id)` live on this port? Discuss admin/maintenance operations versus Interface Segregation — when a fat repository interface starts to hurt.
5. The leaderboard is read-heavy and write-light. Does the *port* need to know that? Where does the read/write asymmetry get addressed (caching adapter, read replica) without leaking into the domain interface?

---

### Task 1.12 — `ICachePort` Protocol

1. `get(key) -> str | None`, `set(key, value, ttl)` — why keep the port's value type `str`/`bytes` rather than `Any`/`dict`? Which concern are you deliberately pushing onto the *caller*?
2. A `get` returns `None`: distinguish the two causes (key absent vs key expired), explain why the cache often can't tell them apart, and why **cache-aside** treats both identically (miss → recompute).
3. Define TTL and explain why active game state in Redis uses one (2h per `CLAUDE.md`). What failure does a missing TTL cause (unbounded memory, leaked sessions)?
4. Cache-aside vs write-through vs write-behind: which does "load from Redis, fall back to Postgres" implement, and what consistency window does it accept?
5. This `FakeCachePort` passes its own isolated test but leaks state between tests when run in a suite:
   ```python
   class FakeCachePort:
       _store = {}
       def get(self, key): return self._store.get(key)
       def set(self, key, value, ttl): self._store[key] = value
   ```
   Find the bug. Separately: why is a hand-written fake like this still preferable to a `Mock` for a stateful collaborator?

---

### Task 1.13 — `DungeonGenerator` BSP algorithm

> *Trimmed to fundamentals — the BSP mechanics themselves carry little senior signal.*

1. `DungeonGenerator(seed)` is a pure function. Explain how you obtain a **seeded, isolated** RNG (`random.Random(seed)`) so generation is reproducible and never touches global `random` state — and why global RNG state is both a testing hazard and a concurrency hazard.
2. BSP is recursive. Python has no tail-call optimisation and a default recursion limit (~1000). At what point does that matter, and when would you convert the recursion to an explicit stack? (The recursion-vs-iteration trade-off in general.)

---

### Task 1.14 — Unit tests for `DungeonGenerator`

> *Reframed to testing fundamentals (property-based testing, coverage quality).*

1. Determinism in tests: how does seeding make a randomised function unit-testable, and what's the difference between asserting the *exact output* (golden/snapshot) and asserting *invariants*?
2. Define **property-based testing** (Hypothesis), then give one invariant of generator output (e.g. "all walkable tiles reachable," "≥1 staircase") that's a far stronger test than any single example. Why does Hypothesis's **shrinking** matter when it finds a failure?
3. The repo has a `.hypothesis/` dir. What is a *flaky* property test, and how do `@seed` / the example database make a Hypothesis failure reproducible in CI?
4. Coverage ≥ 80% is gated in CI. Explain why 100% line coverage still doesn't prove correctness (it measures execution, not assertion strength, nor branch×data combinations), and how **mutation testing** (`mutmut`) probes the quality of your assertions.

---

### Task 1.15 — `EnemyAI` pathfinding

> *Reframed to the data-structures-&-algorithms fundamentals it exercises.*

1. Pathfinding on a grid is graph search. Contrast **BFS** (unweighted shortest path, queue, O(V+E)) with **DFS**, and explain why BFS finds the *shortest* path on an unweighted tile grid while DFS does not.
2. `EnemyAI` is a pure function `(enemy, player, floor) -> Action`. Why is that dramatically easier to test than a method that mutates `Enemy`, and how does it embody the "functional core, imperative shell" idea?
3. Running per-enemy pathfinding every turn is O(enemies × grid). State A*'s complexity and one way to bound total cost as enemy count grows (e.g. only path when an enemy is awake/in range — an algorithmic vs architectural optimisation).

---

### Task 1.16 — `GameService.process_turn()`

1. Return a *new* `Dungeon` vs mutate in place: discuss the trade-offs (testability, undo, aliasing safety vs allocation cost). Which fits a "functional core"?
2. Order of operations matters. Lay out the turn pipeline (validate → apply player action → enemy AI → resolve → new state) and give one concrete bug caused by reordering (e.g. enemies acting on stale positions).
3. `process_turn` needs RNG for damage variance. How do you inject it so the service never touches global `random`, and why does that make the whole turn reproducible from `(state, seed, action)`?
4. Define **domain event**. Give one `process_turn` might emit (`PlayerDied`, `EnemyKilled`) and explain why emitting an event beats calling a side effect (e.g. the Celery trigger) directly from the domain.
5. `GameService` takes everything as parameters (no `__init__` deps). Contrast with constructor-injected repositories: what does the parameter style buy in purity, and what does it cost in caller ergonomics?

---

### Task 1.17 — Unit tests for `GameService`

1. **Fake vs Stub vs Mock vs Spy** (Meszaros/Fowler taxonomy): define each, and say which you'd reach for with a *stateful* collaborator versus when you need to *verify an interaction*.
2. Enumerate the attack-resolution test cases (kill, non-lethal hit, overkill, damage-variance bounds, target out of range). Which edge case is most often forgotten?
3. The board notes `process_turn` needs no fake (it takes no ports). Why does a pure function require zero test doubles, and why is that a *design* win rather than just a testing convenience?
4. Apply **Arrange-Act-Assert** to a "descend stairs" test. Why does one logical assertion per test aid diagnosis when it fails?
5. A `process_turn` test is flaky. List the usual causes in a *pure* domain test (hidden global RNG, `set`/`dict` ordering assumptions, wall-clock time, a shared mutable fixture) and how you'd isolate each.

---

### Task 1.18 — `ScoreService.compute()`

1. Re-derive why `compute` is pure, then explain how injecting the scoring weights lets you support multiple game modes *without editing* `ScoreService`. Name the principle (Open/Closed) and the pattern (Strategy).
2. Where does `item_multiplier` aggregation belong, and why is "compute the multiplier from inventory" a domain rule rather than an adapter concern?
3. An `ABANDONED` dungeon scores `0`. Is that `compute`'s responsibility (a scoring invariant) or the use case's (an orchestration guard)? Pick one and defend it consistently.
4. The formula could be data-driven (weights from config). Weigh the senior trade-off between a flexible config-driven formula and a simple hard-coded one (YAGNI vs premature generalisation).

---

### Task 1.19 — Unit tests for `ScoreService`

1. A pure function with no deps needs no fakes — why? And what does that say about the value-per-line of these tests versus integration tests (the test pyramid)?
2. `pytest.mark.parametrize`: why is it the right tool for a formula with many input combinations, and how does it differ from a loop inside one test in terms of *failure reporting*?
3. Give a **property** of `compute` worth a Hypothesis test (e.g. monotonicity — more kills never lowers the score) and explain why properties catch bugs an example table misses.
4. A score test passes locally but fails in CI. List the environment causes to check first (locale/timezone, Python version, float-vs-int, dependency-pin drift). Why is determinism the precondition for any useful CI signal?
5. What is `conftest.py` for (shared fixtures, config, no import needed), and which Phase-1 fixtures would you centralise there (sample `Dungeon`/`Player` builders)?

---

## Phase 1 — Summary quiz (10 questions, need 9/10)

1. Explain hexagonal / Clean architecture and the **Dependency Rule** in your own words. What single source-code rule enforces it, and how would an `import-linter` contract encode that for `src/domain`?

2. PR review: `from sqlalchemy.orm import Session` appears in `domain/services/game_service.py`. Name the violated principle, the concrete runtime/testing risk, and the fix (define a port, inject it).

3. `Protocol` vs `ABC` — structural vs nominal typing. Give the concrete reason Protocols fit ports here: an adapter can satisfy the interface without ever importing the domain.

4. A player dies in `process_turn`. The app must (a) persist the final state to Postgres, (b) enqueue a Celery leaderboard recalc, (c) return a `GameOver` response to the client. Assign each to a layer and justify with the dependency rule.

5. Why are domain-layer unit tests in this project always fast and infrastructure-free? Point to the *specific architectural property* (pure functions behind ports, no I/O) that guarantees it.

6. Define a **pure function** and name two from this domain. Why does purity make the "functional core" trivially testable and safe to parallelise?

7. The mutable-default-argument gotcha: explain it at the level of *when* the default is evaluated, give the `default_factory` fix, and say why this is a classic senior screening question.

8. The `Score` formula multiplies its factors. Walk through a numeric example, then critique the multiplicative design (zero annihilation) and propose a guard.

9. "Make illegal states unrepresentable": take `Item.effect` (one field with two meanings) and redesign it as a typed union. What entire class of bug disappears?

10. A new dev asks "why not just use our ORM models as domain models?" Give the full senior answer: anemic-domain coupling, persistence concerns leaking, test speed, and the hexagonal boundary.

---
---

## Phase 2 — Persistence adapters

---

### Task 2.1 — `docker-compose.yml`

1. What dev/prod-parity problem does Compose solve (a twelve-factor concern), and what's the danger of dev-only conveniences silently drifting from production?
2. Named volume vs bind mount vs anonymous volume for Postgres data: why a *named* volume, and what data-loss bug does the wrong choice cause on `docker compose down`?
3. `depends_on` orders container *start* but not *readiness*. Why is "postgres container started" not the same as "postgres accepting connections," and what's the correct fix (healthcheck + `condition: service_healthy`, or app-side retry)?
4. The app can't reach Postgres on first boot. Walk the diagnosis order: service-name DNS, port, readiness race, credentials. Which is most common and why?
5. How does Compose's default network let the app reach `postgres:5432` by service name (no hardcoded IP), and why does that matter for reproducibility?

---

### Task 2.2 — Alembic setup + initial migration

1. `--autogenerate` vs hand-written migrations: what does autogenerate *diff*, and name two changes it **can't** detect (e.g. server defaults, some type changes, any data migration).
2. `upgrade head` / `downgrade -1`: what makes a migration reversible, and why are some (dropping a populated column) irreversible in practice?
3. Adding a `NOT NULL` column to a populated table **safely**: describe the expand/contract pattern (add nullable → backfill → set `NOT NULL`) and why a naïve single migration locks or breaks the table.
4. A migration fails halfway through. Which engines wrap DDL in a transaction (Postgres does), and why does transactional DDL save you from a half-applied schema?
5. Why must migrations be checked in and validated in CI (single head / `alembic check`)? What goes wrong when two branches each create a head?

---

### Task 2.3 — SQLAlchemy ORM models

1. ORM model vs domain dataclass: restate the separation and give the two concrete failure modes of merging them (persistence concerns leak into the domain; tests get slow/IO-bound).
2. Define the **N+1 query problem** precisely (one query for the parents, N for the children) and give a `Dungeon → Floors → Enemies` access pattern that triggers it.
3. `lazy="selectin"` vs `"joined"` vs `"subquery"`: describe the query shape each emits and when `selectin` wins (collections; avoids the row multiplication a join causes).
4. SQLAlchemy's **Identity Map** and **Unit of Work**: what do they give you within a session, and how does the identity map prevent two objects for the same primary key?
5. Representing `Dungeon.player` in the schema: foreign key vs embedded JSONB vs separate table — argue the trade-offs (queryability/normalisation vs read-as-a-blob simplicity).

---

### Task 2.4 — `PostgresGameRepository`

1. For mypy to accept `PostgresGameRepository` as an `IGameRepository`, what exactly must match (method names, parameter/return types, variance)? Why is there no `implements` keyword (structural typing)?
2. The adapter's core job is mapping: domain `Dungeon` → ORM → SQL and back. Why does that mapping belong in the adapter, and what's the cost of letting it leak (the domain learns about columns)?
3. `async with session.begin()`: what transaction boundary does it open, and what happens on an exception (rollback) vs a clean exit (commit)?
4. Is SQLAlchemy's session already a Unit of Work? Explain, and say when you'd wrap it in an explicit UoW abstraction for use-case-level atomicity.
5. Async SQLAlchemy + asyncpg: why must the whole call chain be `async`, and what's the classic bug of making a blocking/sync DB call inside an async endpoint?

---

### Task 2.5 — `PostgresScoreRepository`

1. This query is meant to return the global all-time **top 10** but returns the wrong rows:
   ```sql
   SELECT user_id, score FROM scores
   WHERE period = 'all_time'
   ORDER BY score
   LIMIT 10;
   ```
   Find the bug. Then name the index that turns this query into an index scan (e.g. `(period, score DESC)`), and say when a **covering** index would enable an index-only scan.
2. `EXPLAIN` vs `EXPLAIN ANALYZE`: what does each show, and how do you spot a missing index (a seq scan on a large table; estimated-vs-actual row blow-up)?
3. Keyset (cursor) vs `LIMIT`/`OFFSET` pagination: why does deep `OFFSET` degrade, why is keyset the right call for a leaderboard, and what's the cursor-stability caveat under concurrent inserts?
4. Make `save(score)` idempotent against a retry: `INSERT ... ON CONFLICT DO NOTHING/UPDATE` on which unique key? Why is idempotency a *distributed-systems necessity* (at-least-once delivery), not a nicety?
5. Which isolation level do leaderboard *reads* need, and why is Read Committed (Postgres's default) enough here while an in-game currency transfer would want Repeatable Read or Serializable? Mention MVCC.

---

### Task 2.6 — Integration tests for DB repos

1. `testcontainers` vs a shared local DB: what reproducibility/isolation property does an ephemeral container give CI, and how does a shared DB create inter-test coupling?
2. `scope="session"` vs `scope="function"` fixtures: which suits the container (expensive, once) vs per-test data, and what's the speed-vs-isolation trade-off?
3. Two ways to reset state between tests (transaction-rollback-per-test vs truncate/recreate): compare speed and fidelity, and say why rollback-per-test is the common fast default.
4. Where do these sit on the **test pyramid**, and why do you want comparatively *few* of them relative to domain unit tests?
5. A container takes 30s to start in CI and tests time out. Which fix addresses the *root cause* — wait-for-ready healthcheck, session-scoped reuse, or readiness polling?

---

### Task 2.7 — `RedisCache` implementing `ICachePort`

1. Who serialises `Dungeon` before `cache.set`, and in what format (JSON vs pickle)? Why is pickle in a cache a security and portability risk?
2. `SETEX` vs `SET` + `EXPIRE`: why does the atomic single command avoid a TTL-less key if the process dies between two separate commands?
3. `redis.asyncio` vs the sync `redis-py`: why must a FastAPI app use the async client, and what does a blocking Redis call do to the event loop?
4. Why does the app need a Redis **connection pool** rather than a connection per request? Relate it to DB pool sizing (connection-setup cost, file-descriptor exhaustion).
5. Redis is down and `get` raises. Design **graceful degradation**: fall back to Postgres, log at what level, and explain why a *silent* fallback that hides the outage is an anti-pattern.

---

### Task 2.8 — Integration tests for `RedisCache`

1. This round-trip test for `RedisCache` always fails (or emits a coroutine warning) even though the cache works:
   ```python
   async def test_roundtrip(cache):
       await cache.set("k", "v", ttl=60)
       assert cache.get("k") == "v"
   ```
   Find the bug. What single assertion, done correctly, proves serialisation symmetry?
2. Testing TTL expiry deterministically: why is `time.sleep` the wrong tool, and what are the alternatives (fakeredis time control, short TTL + poll, clock injection)?
3. A Redis test passes alone but fails in the suite — most likely a shared-key/shared-DB collision. How do per-test key namespaces or `FLUSHDB` fix it, and which is safer?
4. `fakeredis` vs a real Redis container: what fidelity do you trade for speed, and which Redis features (Lua scripts, certain eviction policies) might `fakeredis` not model faithfully?
5. Should integration tests share the application's Redis instance? Explain the blast-radius risk and the isolation principle for test infrastructure.

---

### Task 2.9 — Supabase Auth setup

1. JWT anatomy: three base64url parts (`header.payload.signature`). Which part carries identity (claims like `sub`), and why is it the **signature** — not encryption — that makes the token trustworthy? (JWTs are signed, not secret.)
2. `anon` vs `service_role` key: which one bypasses Row-Level Security and must never reach the browser? What's the blast radius if `service_role` leaks?
3. `exp` / `iat` / `nbf` claims: what does the server check on every request, and what does the client do once `exp` passes (refresh-token exchange)?
4. The `aud` (audience) claim: what attack does validating it prevent (a token minted for another service being replayed at yours)?
5. Why is "verify the signature with the right key + check `exp` + check `aud`/`iss`" the minimum bar, and what's the classic JWT vulnerability if you accept `alg: none` or fail to pin the algorithm?

---

### Task 2.10 — JWT validation FastAPI dependency

1. `Depends(get_current_user)`: how does FastAPI resolve it, cache it **per request**, and inject the result? Why is per-request caching important when several dependencies all need the user?
2. This `get_current_user` dependency "works" in tests but accepts forged tokens in production:
   ```python
   def get_current_user(token: str = Depends(oauth2_scheme)):
       payload = jwt.decode(token, options={"verify_signature": False})
       return payload["sub"]
   ```
   Find the bug — it's a critical one. Separately, where *should* this function raise `401`?
3. The three things to verify on the token, and which library (`pyjwt` / `python-jose`). What happens if you skip signature verification?
4. `401` vs `403`: define authentication vs authorisation, map each to a game scenario (no token vs accessing another user's game), and which header must accompany a `401` (`WWW-Authenticate`)?
5. Should authorisation (ownership checks) live in this dependency or in the use case? Argue the separation — authN at the edge, authZ next to the resource.

---

### Task 2.11 — Supabase Storage bucket setup

1. Object storage vs a Postgres `BYTEA` column: why offload large blobs (DB bloat, backup size, cache pressure), and what do you lose (transactional consistency with the row)?
2. Public vs private bucket for save files: which, and how does a **pre-signed URL** grant time-bounded access without making the bucket public?
3. Why hand out pre-signed URLs instead of streaming bytes through the FastAPI process (offload bandwidth; avoid blocking the event loop on large transfers)?
4. Key design `saves/{user_id}/{game_id}.json`: what does the prefix structure give you (listing, per-user scoping, lifecycle rules), and what authorisation check must *still* run server-side?

---

## Phase 2 — Summary quiz (10 questions, need 9/10)

1. Explain the repository pattern. Why does `PostgresGameRepository` implement a *domain-defined* port, and what exactly changes (and doesn't) if you swap Postgres for MongoDB?

2. This loop issues hundreds of queries for a handful of dungeons:
   ```python
   dungeons = (await session.execute(select(DungeonORM))).scalars().all()
   for d in dungeons:
       for floor in d.floors:
           total = len(floor.enemies)
   ```
   Find the anti-pattern and name exactly what triggers it here. How would you *detect* it (query counting in a test, or query logging in observability)?

3. Design the schema for `Dungeon → Floors → Enemies` (tables, columns, FKs) and compare it to storing the whole dungeon as one JSONB blob. When is each right (queryability vs read-as-a-blob)?

4. Isolation levels: name the four, the anomaly each prevents (dirty / non-repeatable / phantom read), and pick the right level for leaderboard reads vs an in-game currency transfer. Where does MVCC fit?

5. Connection pooling: why does Postgres's process-per-connection model make pooling essential, what's a sane pool-size starting point, and what does PgBouncer **transaction-mode** break (prepared statements, session state, `LISTEN/NOTIFY`)?

6. Redis goes down in production while the app reads it on every WebSocket message. Describe your fallback, what you log, and how a circuit breaker stops you hammering a dead Redis.

7. Unit vs integration vs e2e — give one Phase-2 example of each and place them on the test pyramid.

8. A request arrives with a JWT bearer token. Trace verification step by step (extract → decode → verify signature → check `exp`/`aud` → load user). Where does each failure return `401`?

9. Under a network retry, this `save` creates duplicate leaderboard rows:
   ```python
   async def save(self, score: Score) -> None:
       await self.session.execute(insert(ScoreORM).values(**asdict(score)))
   ```
   Find what makes it non-idempotent, and name the single SQL clause (on which unique key) that would fix it. Why is this an at-least-once-delivery defence?

10. Migrations: give the zero-downtime expand/contract sequence for adding a `NOT NULL` column to a live, populated table, and explain why each step is ordered the way it is.

---
---

## Phase 3 — Application use cases + API

---

### Task 3.1 — `StartGame` use case

1. Use case vs domain service: define each (orchestration of ports + domain vs a pure business rule) using `StartGame` and `GameService` as the examples.
2. Order the steps (create domain `Dungeon` → persist → cache the first floor) and assign each to a layer. Why does the *use case*, not the domain, own this sequence?
3. `user_id: UUID` vs a `Player` object as input: which, and why does a use case taking primitive identifiers at its boundary aid decoupling from the transport layer?
4. The DB save succeeds but the cache write fails. What consistency state results, and how do you handle it (cache is rebuildable derived state — don't fail the command)?
5. Is `StartGame` a **Command** (Command pattern / CQRS write side)? What does modelling writes as explicit commands buy you (a single entry point, audit, queueability)?

---

### Task 3.2 — `ProcessTurn` use case

1. Why load mid-game state from Redis, not Postgres? What is the cache's role (hot mutable state) vs Postgres's (checkpoints), and what durability risk do you knowingly accept?
2. Two moves arrive nearly simultaneously for one session. Describe the read-modify-write **race** precisely, then give two fixes (per-session lock, optimistic version check, or a single serialised consumer).
3. What's in the response payload back to the WS handler, and why a versioned/typed event rather than a raw dict?
4. Where does state persist after a turn (Redis every turn, Postgres on checkpoints)? Justify the write-amplification trade-off.
5. The player dies this turn. How does it differ from a normal turn (emit game-over, kick off the submit-score path, stop accepting actions)? Why is this a *state transition*, not just another turn?

---

### Task 3.3 — `SubmitScore` use case

1. Why enqueue `score_recalc` to Celery instead of rebuilding the leaderboard inline (latency budget, failure isolation, don't block the request on heavy work)?
2. You can't hand a `Dungeon` object to a Celery task. What do you pass instead (an id / minimal serialisable payload), and why does this tie back to the JSON-not-pickle serialiser choice?
3. Idempotent `SubmitScore`: a retried submission must not double-count. What key makes it idempotent, and where do you enforce it (DB unique constraint vs app check)?
4. Cleaning the Redis game state: before or after the durable DB write? Order it so a crash can never lose an unsaved score.
5. After submit, the leaderboard is **eventually consistent** (recalc is async). Describe the user-visible window and why it's acceptable here.

---

### Task 3.4 — FastAPI app setup

1. The `lifespan` context manager replaces deprecated `on_event`. Which two resources do you init/teardown there (DB engine, Redis pool), and why is startup the right place rather than module import?
2. ASGI vs WSGI: why does an async, WebSocket-capable app require ASGI, and what can't WSGI do?
3. Middleware runs LIFO around the handler. Give an ordering bug caused by getting it wrong (e.g. CORS after auth, or an error-logging middleware that never sees handler exceptions).
4. `Depends()` for a per-request DB session: how does a `yield`-dependency provide setup/teardown, and why is request scope the right lifetime?
5. CORS: which same-origin restriction does it relax, and why is `allow_origins=["*"]` together with credentials a misconfiguration?

---

### Task 3.5 — Auth endpoints

1. `access_token` vs `refresh_token`: their lifetimes, where each is sent, and why short-lived access + long-lived refresh limits the blast radius of a leaked token.
2. Should the backend store passwords? If you hashed locally, which algorithm family (argon2/bcrypt, never a fast hash) and why salt + slow? Here Supabase owns it — what does that change about your responsibility?
3. Wrong-password login returns `401`, not `403`. Restate the authN-vs-authZ distinction and why `403` would imply "authenticated but forbidden."
4. Why is `Authorization: Bearer <token>` preferred over a cookie for an API, and what does that imply about CSRF exposure (a header isn't auto-sent → less CSRF, but more XSS token-theft surface)?
5. Statelessness: why does putting identity in a *verifiable token* (vs a server-side session) make horizontal scaling easier? Tie to the twelve-factor "stateless processes" rule.

---

### Task 3.6–3.8 — Game REST endpoints

1. `POST /game/start`: `201 Created` vs `200 OK`, and what belongs in the body plus the `Location` header when you create a resource?
2. A missing game returns `404`. Which layer decides this (the use case maps "repo returned `None`" → not-found; the router translates it to HTTP)? Why shouldn't the repository raise HTTP errors?
3. `POST /game/{id}/abandon`: is it idempotent? *Should* it be? How do `PUT`/`DELETE` idempotency semantics inform the design (a repeat lands in the same state)?
4. A user requests another user's game: `404` vs `403`? Argue the security trade-off (`404` hides existence). Where does the ownership check live?
5. `PUT` vs `PATCH` vs `POST` for state changes: map "abandon" to the right method and justify it with the safe/idempotent method definitions.

---

### Task 3.9 — WebSocket turn loop

1. The WS lifecycle in Starlette: list the stages (HTTP `Upgrade` handshake → `accept` → receive/send loop → close). What status code is the upgrade handshake?
2. Browsers can't set custom headers on a WebSocket. How do you authenticate it (token in query param, first-message auth, or cookie), and what's the trade-off of each (URL logging vs handshake complexity)?
3. `process_turn` raises mid-connection. What should the handler do (catch, send an error frame, decide close vs continue)? Why must one bad message not silently kill the loop?
4. The player closes the tab. How does the server detect the dropped connection, and how do you clean up the Redis session state and avoid leaked tasks?
5. A fast client floods actions. What is **backpressure**, and how do you bound it (single in-flight turn per session, drop/queue policy)?

---

### Task 3.10–3.12 — Leaderboard endpoints

1. Cache-key design for `/leaderboard/global`, and cache-aside miss handling (recompute → populate → set TTL). What staleness window do you accept?
2. **Cache stampede** / thundering herd on a cold key with 1,000 concurrent requests: describe it and give two mitigations (single-flight lock, early/jittered recompute).
3. `/leaderboard/me` needs the user id with no DB hit. How does the verified JWT supply it (identity from claims = stateless)?
4. Should a top-100 endpoint be paginated? Argue both sides; if you paginate, keyset vs offset and why.
5. A new high score just landed but the cache is 5-minutes stale. When does it appear, and how would write-through or explicit invalidation change that — at what cost?

---

### Task 3.13 — Pydantic v2 schemas

1. Pydantic model vs SQLAlchemy model vs domain dataclass — three distinct roles. Why does the API schema sit at the boundary doing "parse, don't validate"?
2. `ConfigDict(from_attributes=True)`: what does it enable (object/ORM → schema), and why is it the bridge from domain/ORM objects to response models?
3. `field_validator` vs `model_validator` (`mode='before'` / `'after'`): give one concrete example of each (a single-field bound check vs a cross-field invariant).
4. Pydantic v2's Rust core (`pydantic-core`): why is it dramatically faster than v1, and which v1→v2 migration gotchas bite (`.dict()` → `.model_dump()`, the validator API change)?
5. Hiding `email` / internal id from `PlayerResponse`: a dedicated output schema vs field exclusion on a shared one — why is a separate response schema the safer default (no accidental over-exposure)?

---

### Task 3.14–3.15 — Tests

1. `TestClient` (sync, httpx underneath) vs `httpx.AsyncClient`: when do you genuinely need the async client (real async paths, WebSockets), and what does `TestClient` hide?
2. Overriding `get_current_user` via `app.dependency_overrides`: why is DI-based override cleaner than monkeypatching, and what does it let you test (endpoints without real auth)?
3. `pytest.mark.asyncio` (or anyio): when is it required, and what's the event-loop-scope pitfall across tests?
4. Real DB vs fake repository for API tests: state the fidelity-vs-speed trade-off and where you'd draw the line (use-case tests with fakes; a few e2e with real infra).
5. Testing the WS turn loop: structure of an async WS test (connect → send → assert received event). Why is this closer to e2e than to a unit test?

---

## Phase 3 — Summary quiz (10 questions, need 9/10)

1. Trace the full call stack when a WS message arrives with `{"action":"attack"}` — from the WebSocket handler down to the domain and back up. Name each layer and what it does.

2. Use case vs domain service, using `ProcessTurn` and `GameService` — orchestration vs pure rule.

3. FastAPI leans on dependency injection. Explain `Depends()` (resolution + per-request caching) and give two examples from this project (DB session, current user).

4. The `ProcessTurn` double-move race: describe it precisely and give two application-level preventions (per-session lock, optimistic version).

5. Map HTTP status codes to: (a) game not found, (b) authenticated request but no token, (c) authenticated but accessing another user's game, (d) DB crash mid-request — and state the principle behind each.

6. `/leaderboard/global` must respond in < 50 ms. Trace the layers on a cache hit and explain what keeps each fast; then describe what happens on a miss.

7. Idempotency across the stack: where does it matter (`SubmitScore`, abandon, score save) and what mechanism enforces it at each point?

8. Describe the full WebSocket authentication flow — from the client opening the connection to the server confirming identity — without custom headers.

9. Resilience under load: a client floods turns while a downstream is slow. Place each of rate limiting, single-flight, timeout, and circuit breaker where it belongs and say what each protects.

10. Pydantic as the boundary: how does "parse, don't validate" at the edge keep invalid data out of the domain, and what does the domain therefore get to *assume*?

---
---

## Phase 4 — Celery workers

---

### Task 4.1 — Celery app setup

1. What does Celery give you that `asyncio` cannot? Frame it as offloading work to *separate processes/hosts* with durability and scheduling — and connect it to the I/O-bound vs CPU-bound distinction (asyncio helps in-process I/O concurrency; Celery distributes work, including CPU-bound jobs the GIL would otherwise serialise).
2. Broker vs result backend: what does each store (pending task messages vs return values/state), and why can you run without a result backend?
3. Redis vs RabbitMQ as the broker: what does Redis trade away (true AMQP routing, stronger delivery guarantees) for operational simplicity here?
4. The worker process vs the FastAPI process: why keep them separate, and how does that isolate a heavy or blocking job from the request path?
5. `task_serializer="json"` not `"pickle"`: explain the remote-code-execution risk of unpickling untrusted task payloads, why JSON is the safe default, and what it costs (only JSON-serialisable args).

---

### Task 4.2 — `score_recalc` task

1. "Rebuild the leaderboard" — what does it read (score rows) and write (a sorted cache / Redis ZSET)? Why is re-running it safe (idempotent by construction)?
2. Why offload it asynchronously rather than running it inline in `SubmitScore` (latency budget, failure isolation)?
3. `@app.task(bind=True)`: what does `self` give you (retry, request id, task state)?
4. **At-least-once delivery** means the task can run twice. Why must `score_recalc` be idempotent, and what would double execution corrupt if it weren't?
5. During a Redis outage, this task config makes the outage *worse* across a fleet of workers:
   ```python
   @app.task(autoretry_for=(RedisError,), max_retries=3)
   def score_recalc():
       ...
   ```
   Find what's missing and the failure mode it causes (think synchronised retries / thundering herd).

---

### Task 4.3 — `map_generation` task

> *Kept lean — the engineering content here is offload, dedup, and async-result coordination.*

1. CPU-bound BSP for deep floors is offloaded to a worker. Why does running it inline risk blocking, and how does this map to the I/O-bound vs CPU-bound rule (asyncio won't parallelise pure-Python CPU work under the GIL; a separate *process* will)?
2. Ensuring only one task runs per `(game_id, floor_index)` even if triggered twice: dedup via a lock key or a deterministic task id. Why is true "exactly once" generally unachievable, making "effectively once via idempotency" the real goal?
3. Where's the result stored, and how does the requester learn it's ready (poll a cache key / pub-sub)? This is the async-result coordination problem.
4. The player dies before descending, orphaning the pre-generated data. Who cleans it up and via what mechanism, and why is **TTL-based** cleanup more robust than relying on an explicit delete?

---

### Task 4.4 — `weekly_leaderboard_reset` task

1. List the steps in order (archive → wipe → optionally notify). Why archive *before* wiping (no destructive op without a durable copy first)?
2. A race with a concurrent `score_recalc`: describe the interleaving that corrupts state, then prevent it with a distributed lock (Redis `SET NX`, and the Redlock caveats) or scheduling exclusion.
3. The task crashes halfway. How do you make it safe to retry (idempotent steps, transactional archive, checkpointing)?
4. Should it also email users their ranking? Argue Single Responsibility — a separate notification task — and what coupling that avoids.
5. Celery Beat vs cron: what does Beat give a containerised app (in-app, timezone-aware schedule; no host crontab), and what's the single-Beat-instance constraint?

---

### Task 4.5 — Celery Beat schedule

1. This Beat entry is supposed to run the reset **weekly** but runs it far more often:
   ```python
   beat_schedule = {
       "weekly-reset": {
           "task": "tasks.weekly_leaderboard_reset",
           "schedule": crontab(minute=0, hour=0),
       }
   }
   ```
   Find the bug. Then explain how Celery interprets the corrected schedule (UTC vs configured timezone).
2. Two Beat instances on the same schedule → duplicate dispatch. Why must Beat be a singleton, and how do you guarantee that (single replica / leader lock)?
3. `crontab` vs `timedelta` schedule types: when each fits (wall-clock-aligned vs interval-since-last-run).
4. How does Beat persist its schedule state, and what happens to a missed run across a Beat restart — does it backfill?
5. Running at midnight **Warsaw** time (CET/CEST — DST!): how do you configure the timezone, and why is hardcoding `+01:00` a daylight-saving bug?

---

### Tasks 4.6–4.7 — Docker Compose + testing

1. A worker service in Compose reuses the app image with a different command and shares the broker and code. Why the *same* image (build once, run many roles)?
2. Test that `SubmitScore` enqueues `score_recalc` without a real worker: assert on the `.delay`/`apply_async` call (mock the task). You're testing the *interaction*, not the task body — why is that the right seam?
3. `task_always_eager`: what does it do in tests (run inline, synchronously), and what does eager mode *not* faithfully exercise (serialisation, the broker, real retries)?
4. `apply_async()` vs `delay()`: the relationship (`delay` is the shortcut) and when you actually need `apply_async` (`eta`, `countdown`, queue routing).
5. Two ways to test a task without a broker (eager mode vs calling the underlying function directly): the fidelity trade-off between them.

---

## Phase 4 — Summary quiz (10 questions, need 9/10)

1. Celery vs the Celery worker vs Celery Beat: draw their interaction in text (producer → broker → worker; Beat → broker on schedule).

2. `score_recalc` must be idempotent. Define idempotent and describe how you implement it for a leaderboard rebuild — and why at-least-once delivery makes it mandatory.

3. A task fails. First name the three outcomes depending on retry configuration. Then find the bug in this decorator — it retries things it never should, and never gives up:
   ```python
   @app.task(autoretry_for=(Exception,), retry_backoff=True)
   def score_recalc():
       ...
   ```

4. `weekly_leaderboard_reset` runs while `score_recalc` is running. Describe the race and one prevention using a Redis lock — and mention Redlock's caveats.

5. `task_serializer="json"` vs `"pickle"`: make the remote-code-execution argument for why pickle is dangerous in production.

6. A worker crashes mid-task. What happens to the message in the broker? Explain task acknowledgement, `acks_late`, and the at-most-once vs at-least-once trade-off (and the duplicate-execution risk).

7. This schedule is meant to fire at **Warsaw midnight** but fires at the wrong local hour for half the year:
   ```python
   # celery config: timezone = "UTC"
   crontab(minute=0, hour=0, day_of_week="mon")
   ```
   Find what's missing and the seasonal (DST) bug that leaving it causes.

8. `map_generation` pre-generates floor 6 when the player descends to floor 5. Describe the whole flow from the WS handler triggering the task to the player receiving floor 6 (including how readiness is signalled).

9. Test a Celery task with no running broker. Name two approaches (eager mode, direct call) and the trade-offs of each.

10. `score_recalc` reads 10,000 rows to rebuild the leaderboard and is slow. Give two optimisations — one at the query level (server-side `ORDER BY ... LIMIT` on an index) and one at the cache level (incremental `ZADD` update instead of a full recompute) — and discuss incremental vs full recompute.

---
---

## Phase 5 — React frontend

> The backend is the star. These quizzes drill the *transferable* frontend-senior fundamentals —
> rendering model, hooks, state, data fetching, and web security — and deliberately skip pixel-art and
> canvas trivia, which carry no senior-engineering signal for your goals.

---

### Task 5.1 — Vite + React setup

1. Vite's dev server uses native ESM + esbuild. Why is its cold start and HMR faster than CRA's "bundle everything with webpack" model?
2. **Tree-shaking**: what is it, what enables it (static ES-module imports), and why does it shrink the production bundle?
3. TypeScript for this project: one strong reason for (a shared, checked WS event contract) and one reason against (overhead/ceremony).
4. The Vite dev proxy: why proxy `/api` to the backend in development, and which CORS/cookie problem does that sidestep?

---

### Task 5.2 — Pixel tile set design

> *Trimmed to the single transferable idea.*

1. A sprite sheet packs many tiles into one image. State the one engineering reason that generalises beyond games — request batching / a single decode — and name another place the *same* principle shows up (e.g. GraphQL DataLoader batching, HTTP/2 multiplexing, DB batch fetching).

---

### Task 5.3 — Canvas renderer

> *Trimmed to the rendering-loop and separation-of-concerns ideas.*

1. `requestAnimationFrame` vs `setInterval`: why does rAF align with the display refresh and pause on a hidden tab, and how is "let the platform schedule the work" a general performance principle?
2. Why decouple *rendering* (draw from current state) from *state updates* (game events)? Relate it to React's "UI is a function of state" model and to separating a read model from a write model.

---

### Task 5.4–5.5 — Sprites and animation

> *Trimmed to the one React fundamental it teaches.*

1. Per-frame animation state (current frame, last-frame time) belongs in a `useRef`, not `useState`. Why? (Mutating it must *not* trigger a re-render.) State the general rule: `ref` for mutable values that shouldn't cause renders, `state` for values the UI is derived from.

---

### Task 5.6 — `useGameSocket` hook

1. The two **Rules of Hooks** (top level only; only in React functions) — and *why* they exist (hook identity is positional: call order must be stable across renders).
2. The WS lifecycle in a `useEffect` with cleanup: why must the cleanup close the socket, and what bug does a missing cleanup cause (leaked sockets, double-connect under StrictMode)?
3. A state update arrives → a re-render is triggered. How does setting state propagate, and how do you avoid re-rendering the whole tree on every ~10 Hz update (memoisation, state colocation, splitting components)?
4. `useRef` vs `useState` inside the hook: which holds the socket instance and why (stable identity, no re-render when it changes)?
5. `sendAction` stability via `useCallback`: why does an unstable function reference cause effect re-runs and child re-renders, and how does `useCallback` fix it?

---

### Task 5.7 — Keyboard input handler

1. `keydown` vs `keyup` for turn-based input — which, and how do you stop OS key-repeat from firing many turns from one held key?
2. Why register the listener in a `useEffect` (on `document`) with a cleanup, and what leaks if you don't remove it?
3. Gating input during text entry (the login form): how do you ignore game keys when an input element is focused (check the event target)?
4. Preventing an action flood before the server acknowledges the first — single-flight / disable-until-ack. Note this is the *same* backpressure idea as on the server side.

---

### Task 5.8–5.9 — HUD and game over screen

1. State shape for incoming game state: why one normalised object over many separate `useState` calls, and how does that avoid inconsistent partial updates?
2. Model the game-over transition (`event.type === "game_over"`) as an explicit **state machine**. Why are named states better than scattered booleans (`isDead`, `isPlaying`, `isOver`)?
3. HUD as HTML-over-canvas vs drawn-on-canvas: the trade-off (accessibility, layout, crisp text vs a single render surface). Which fits a backend-focused portfolio app, and why?

---

### Task 5.10–5.11 — Leaderboard and auth screens

1. Fetching `/leaderboard/global`: raw `useEffect` + `fetch` vs React Query / SWR — what do the libraries solve (caching, request dedup, stale-while-revalidate, retries)?
2. Handling loading / error / empty states explicitly: why is "render only the happy path" a classic junior bug, and how do these states map to the request lifecycle?
3. JWT storage — `localStorage` vs `sessionStorage` vs an in-memory variable: rank them by XSS exposure and explain the trade-off against persistence/refresh UX.
4. XSS vs CSRF: define both, say which threatens a `localStorage` JWT and which threatens cookie auth, and give the mitigation for each (CSP/output-escaping vs `SameSite`/anti-CSRF tokens).
5. A `PrivateRoute` (route guard): how does it redirect unauthenticated users, and why is client-side guarding *UX only* — what must the server still enforce?

---

### Task 5.12 — Supabase JWT auth flow

1. Walk the end-to-end flow: login → store session → attach the token to API/WS calls → refresh on expiry.
2. The token expires mid-game. How does the client detect it (`401`, `onAuthStateChange`, or an `exp` check) and recover **without losing game progress**?
3. Attaching a JWT to a WebSocket without custom headers — the same query-param / first-message options as the backend task. Which is least bad, and why?
4. Why is client-side auth state never the security boundary? What does the server independently verify on every request and every WS message?

---

## Phase 5 — Summary quiz (10 questions, need 9/10)

1. Explain React's rendering model: when does a component re-render, and how do you keep a ~10 Hz WebSocket feed from re-rendering the whole world (memoisation, refs, state colocation, component splitting)?

2. `useState` vs `useRef` vs `useReducer`: give one game example of each (HP display / the socket instance / complex turn state).

3. This hook connects fine but leaks a socket on every re-render/remount (and double-connects under StrictMode):
   ```jsx
   useEffect(() => {
     const ws = new WebSocket(url);
     ws.onmessage = (e) => setState(JSON.parse(e.data));
   }, [url]);
   ```
   Find the bug. Separately: why reconnect with *backoff* rather than immediately?

4. JWT storage security: rank `localStorage` / `sessionStorage` / in-memory by XSS blast radius and give your decision with reasoning.

5. `useCallback` and `useMemo`: give one concrete `useGameSocket` example where each prevents a real performance bug — and note why *over*-memoising is itself a smell.

6. XSS and CSRF: which one is the real risk for this app's bearer-token model, and what's the mitigation (CSP, escaping, keeping the token out of script-readable storage)?

7. Data fetching: what do React Query / SWR give you over `useEffect` + `fetch`, mapped onto the request lifecycle (loading / error / stale / refetch)?

8. "UI is a function of state": how does that principle simplify reasoning, and where does the imperative canvas escape hatch (refs) fit without breaking it?

9. Client guards vs server authorisation: why is `PrivateRoute` UX-only and the server the real boundary?

10. The token expires mid-game: give the exact sequence to refresh and continue without the player losing progress, and why optimistic local state + server reconciliation helps.

---
---

## Phase 6 — Docker + AWS deploy

---

### Task 6.1–6.2 — Dockerfiles

1. Multi-stage build: how does a builder stage plus a slim runtime stage shrink the final image *and* reduce attack surface (no build toolchain in production)?
2. Why copy `pyproject.toml`/`uv.lock` before the source? Explain Docker layer caching and why dependency install shouldn't re-run on every source edit.
3. `CMD` vs `ENTRYPOINT`: the difference, and how the Celery image reuses the same image with only a different command.
4. `--no-cache-dir`, not running as root, pinning the base image by digest — give the production-hygiene reason for each.
5. Reproducible builds: why do `uv sync --frozen` + a pinned `.python-version` matter for "behaves identically in CI and prod"?

---

### Task 6.3 — `docker-compose.prod.yml`

1. List four dev→prod differences (no hot reload, gunicorn-managed uvicorn workers, secrets from a store not the file, resource limits, healthchecks).
2. Why run `gunicorn` managing `uvicorn` workers in production (process supervision, multi-core) rather than a lone `uvicorn`? How many workers — and what's the async caveat (workers × one event loop each)?
3. A Docker healthcheck for FastAPI: which endpoint, and how does the orchestrator use the result (restart, remove from routing)?
4. `restart: always` limits — what it won't fix (crash loops, bad config), and why an orchestrator (ECS) supersedes it in real production.
5. Twelve-factor config: why config via environment, not baked into the image, and how that lets one image run in every environment.

---

### Task 6.4 — GitHub Actions CI

1. Workflow / job / step anatomy and triggers. What does the `preflight` skip-jobs pattern buy you (merging the pipelines before the code exists)?
2. `actions/cache` for the uv/venv: what does it speed up, and what's the cache-key correctness concern (key off the lockfile hash)?
3. Why gate on ruff + black + mypy + pytest coverage ≥ 80%? What does each catch, and how does mypy on `src` help enforce the "no `Any` in domain" rule?
4. Postgres/Redis service containers in CI: how do integration tests reach them, and why is this closer to production than mocking?
5. Fail-fast vs run-all in a matrix: the trade-off, and why **required status checks** are what actually protect `main`.

---

### Task 6.5 — AWS VPC setup

1. VPC: why every production deploy needs network isolation, and what makes a subnet public vs private (a route to an internet gateway).
2. NAT Gateway: why private-subnet tasks need it for *outbound* calls (pulling images, reaching Supabase) without being publicly reachable.
3. Security Group (stateful) vs Network ACL (stateless): the difference, and why SGs are the primary control you reach for.
4. SG rules for ECS → RDS: state the exact rule (allow `5432` *from the app's SG*, not from a CIDR) and why referencing SGs beats IP ranges (least privilege, elasticity).
5. Why put RDS and ElastiCache in private subnets with no public IP — the defense-in-depth / blast-radius argument.

---

### Task 6.6–6.7 — RDS + ElastiCache

1. RDS vs self-managed Postgres on EC2: what AWS operates for you (backups, patching, failover) and what you give up (superuser, arbitrary extensions).
2. Multi-AZ: which failure it covers (an AZ/instance failure via standby failover) and what it does *not* do (it's HA, not read scaling — that's read replicas).
3. One RDS parameter-group setting you'd tune for this workload (e.g. `max_connections` relative to your pooler, or `work_mem`) and why.
4. ElastiCache vs Redis-in-a-container: managed failover, backups, in-VPC placement — and what durability you should (not) expect from a cache.
5. Redis cluster mode: when sharding across nodes is warranted vs a single primary + replica, and the multi-key-operation constraint sharding introduces.

---

### Task 6.8–6.9 — ECS Fargate + ALB

1. Fargate vs ECS-on-EC2: serverless containers (no node management) vs the control/cost trade-off.
2. A Task Definition's contents (image, CPU/memory, env/secrets, ports) — why it's the immutable unit of deployment.
3. An ECS **Service** vs a standalone **Task**: desired-count / self-healing / rolling deploys vs a one-shot run.
4. An ALB operates at **Layer 7**. What does L7 enable (path routing, host headers, TLS termination) that an L4 NLB can't?
5. WebSockets through an ALB: what must be configured (HTTP/1.1 `Upgrade` support, a longer idle timeout, maybe stickiness), and why do long-lived connections complicate scale-in?

---

### Task 6.10–6.11 — CD + HTTPS

1. The CD pipeline from merge to running task: build → push to ECR → register a new task def → update the service → wait for healthy → roll back on failure.
2. ECR vs Docker Hub for AWS: IAM-based auth, same-region pull speed, and avoiding Docker Hub rate limits.
3. An ACM certificate on the ALB: TLS terminates at the load balancer — what's encrypted where, and what's the end-to-end-TLS (re-encrypt to the task) alternative and its trade-off?
4. A Route 53 record pointing `hexcrawl.com` at the ALB: alias `A` record vs `CNAME` — why an alias for an AWS resource?
5. Injecting `DATABASE_URL` at runtime: Secrets Manager / SSM vs plaintext in the task-definition env. Why does the plaintext route leak (visible in the console/API), and why is the secret store the secure path? Tie it to twelve-factor config + least privilege.

---

## Phase 6 — Summary quiz (10 questions, need 9/10)

1. Describe the full production AWS architecture for HexCrawl: name every service (VPC, subnets, NAT, ALB, ECS Fargate, ECR, RDS, ElastiCache, ACM, Route 53, Secrets Manager, CloudWatch) and its role.

2. This Dockerfile builds correctly but reinstalls every dependency on every code change:
   ```dockerfile
   FROM python:3.12 AS builder
   WORKDIR /app
   COPY . .
   RUN uv sync --frozen
   FROM python:3.12-slim
   COPY --from=builder /app /app
   CMD ["uvicorn", "src.entrypoints.http.main:app", "--host", "0.0.0.0"]
   ```
   Find the line that defeats Docker layer caching and explain the fix. Separately, why is the two-stage split smaller and safer than a single stage?

3. A new ECS task crash-loops on deploy. How do you investigate? Order the tools: CloudWatch logs, the task stopped-reason, health-check config, exec-into-task.

4. Why place RDS and ElastiCache in private subnets — the defense-in-depth argument.

5. CD triggers on merge to `main`. List the ordered steps from push to a running ECS task, including rollback.

6. RDS Multi-AZ vs a read replica: different problems (HA vs read scaling). When would you use each?

7. The ALB health check is failing. Give the three most common causes (wrong path, SG blocking the LB, slow start / port mismatch) and how to diagnose each.

8. Your ECS task needs `DATABASE_URL` at runtime. Describe two ways to inject it and explain why plaintext env in the task definition is the insecure choice.

9. Horizontal vs vertical scaling: define both, and explain how Fargate service auto-scaling implements horizontal scaling (target tracking on CPU / request count).

10. WebSocket connections drop when ECS scales in (removes a task). Describe the problem and two mitigations (connection draining, client reconnect-with-backoff), and why stateless servers + external session state (Redis) make this survivable.

---

## Project-wide decisions quiz (10 questions, need 9/10)

> Covers the late-Phase-1 BSP / AI design choices and the cross-cutting v1 trade-offs (logging, feature flags, CI gates, license) recorded in `QUESTIONS.md`. Take this once the corresponding tasks are implemented — you should be able to defend each call without looking at the answers.

1. `DungeonGenerator` caps BSP recursion depth at 5, producing at most 32 leaf rooms on an 80×50 floor. Explain *both* failure modes: what goes wrong if you push recursion deeper (e.g. 8), and what goes wrong if you make it shallower (e.g. 2)?

2. After the corridor pass, the generator runs a flood-fill from the spawn tile to verify every walkable tile is reachable. What category of bug is this check designed to catch, and why is the policy "regenerate with a bumped sub-seed on failure" preferable to "trust the algorithm" *or* to "patch the orphan room with a new corridor"?

3. Enemy and item placement are deliberately split out of `DungeonGenerator` into a downstream `populate_floor(floor, depth, rng)` step. Name two distinct benefits this split provides — one related to testing, one related to balance tuning — and explain why both depend on the same RNG (or split sub-RNGs from the parent seed) being threaded through.

4. The AI design rejects blind Manhattan pathing in favour of line-of-sight gating. What player-visible design problem does blind pathing create, and why is reusing "WALL and closed DOOR block LOS" (decided in task 1.3) for both ranged-attack targeting *and* AI awareness a desirable single-rule outcome rather than coincidence?

5. HexCrawl uses **symmetric** shadowcasting for FOV. State precisely what the "symmetric" invariant means, and describe one concrete combat-fairness bug that asymmetric FOV (e.g. Bresenham raycasting) would produce.

6. Enemy wake-up uses `chebyshev_distance(enemy, player) ≤ 8 AND has_los(enemy, player)`, and once an enemy is awoken it stays awoken for the rest of the floor. Justify each of the three design choices: (a) why AND rather than OR, (b) why 8 specifically, and (c) why sticky aggro rather than releasing on LOS-break.

7. HexCrawl logs structured JSON to stdout only — no direct application-level integration with CloudWatch / Loki / Datadog. Which twelve-factor principle does this implement, and walk through the concrete code-change cost of switching from CloudWatch to Loki under this approach versus under a "library calls the collector directly" approach.

8. Feature flag systems (Unleash, GrowthBook, etc.) were considered and rejected for v1. Give the rejection reason in one sentence, then describe one concrete future scenario where reconsideration would be justified — and why the simplest reasonable response in that scenario is *not* a SaaS flag service.

9. The `import-linter` CI gate is deliberately scheduled to land at the Phase 1 → Phase 2 boundary, not earlier and not later. What hexagonal-architecture risk *first appears* in Phase 2 (and why couldn't it appear in Phase 1)? What concrete cost do you pay by retrofitting the gate after, say, Phase 3 is done?

10. HexCrawl is MIT-licensed. Given the project framing in `CLAUDE.md` ("portfolio centrepiece… vehicle for learning"), what concrete value do you lose by choosing **Apache-2.0** instead, and what concrete value do you lose by choosing **proprietary**? Name one situation where the MIT default would be the wrong call.
