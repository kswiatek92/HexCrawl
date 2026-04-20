# HexCrawl — Quizzes

**How to use**: Tell Claude `"Quiz me on HexCrawl task 1.3"` or `"Quiz me on HexCrawl Phase 1"`.
Claude will ask questions from this file one by one, grade each answer in real time, and finish with
a full profile assessment: overall score, strong areas, weak spots, and specific things to revisit.

**Pass threshold**: 90% per quiz. For 5-question quizzes: 5/5. For 10-question quizzes: 9/10.

---

## Phase 1 — Domain core

---

### Task 1.1 — Repo structure

1. You have a `DungeonGenerator` that takes a `seed: int` and returns a `Floor`. Where in the project does this class live, and why?
2. What is the single rule that governs which direction imports are allowed to flow in hexagonal architecture?
3. A colleague puts `from fastapi import HTTPException` inside `domain/services/game_service.py`. What is wrong with this, and what should they do instead?
4. What is the difference between `domain/` and `application/` in this project?
5. Why do `adapters/` exist as a separate layer rather than just putting database code directly in the routers?

---

### Task 1.2 — `Player` dataclass

1. Why use a `dataclass` instead of a regular class for `Player`? Name two concrete benefits in this codebase.
2. What does `@dataclass(frozen=True)` give you, and would you apply it to `Player`? Why or why not?
3. What is the difference between `field(default_factory=list)` and `field(default=[])`? Which one is correct, and what breaks if you use the wrong one?
4. Should `Player` know how to save itself to the database? Explain your answer in terms of hexagonal architecture.
5. If you need to add `last_seen: datetime` to `Player`, where does the value come from — the domain or an adapter — and why?

---

### Task 1.3 — `Enemy` dataclass + `BehaviourType` enum

1. What is a Python `enum` and why is it preferable to using plain string constants like `"melee"` or `"ranged"` for behaviour types?
2. What does `enum.auto()` do, and when would you use it over explicit integer values?
3. You have `class BehaviourType(str, Enum)`. What does inheriting from `str` give you beyond a plain `Enum`?
4. An `Enemy` has a `behaviour: BehaviourType`. Later the game logic does `if enemy.behaviour == "melee":`. Will this work if `BehaviourType` is a `str` enum? What are the risks?
5. Should `Enemy` have a method like `enemy.attack(target: Player) -> int`? Argue both sides and give your conclusion.

---

### Task 1.4 — `Item` dataclass + `ItemType` enum

1. `ItemType` has values like `HEALTH_POTION`, `SWORD`, `SHIELD`. A new item type needs to be added. What files change, and what files should NOT need to change if your design is correct?
2. What is the difference between a domain model (`Item` dataclass) and a database model (SQLAlchemy `ItemORM`)? Why do we keep them separate?
3. `Item` has an `effect: int` that means different things depending on `ItemType` (damage bonus for weapons, HP for potions). Is this a good design? What would you do instead?
4. Explain the concept of "tell, don't ask" with an `Item` example.
5. Should items be mutable or immutable in the domain model? What are the trade-offs?

---

### Task 1.5 — `Floor` model

1. `Floor` has a `tiles: list[list[TileType]]` grid. What are the coordinates convention trade-offs between `tiles[row][col]` vs `tiles[x][y]`? Which did you choose and why?
2. A `Floor` is generated once and then only read during gameplay. What does this suggest about whether it should be mutable or frozen?
3. How would you verify in a unit test that `DungeonGenerator` always places at least one staircase on every floor?
4. `Floor` holds a `list[Enemy]`. Who is responsible for adding/removing enemies from this list — the `Floor` itself, `GameService`, or `EnemyAI`? Justify your answer.
5. What is the maximum memory cost of a `Floor` with a 50×50 tile grid of `TileType` enum values? Is this a concern?

---

### Task 1.6 — `Dungeon` model

1. `Dungeon` has a `seed: int`. Why store the seed rather than the pre-generated floors? What does this allow?
2. What is the difference between `current_floor_index` and a reference to the current `Floor` object? Which approach did you use and why?
3. `Dungeon` contains a `Player`. Does this mean `Player` is a child of `Dungeon` in the domain sense? What are the implications for serialisation?
4. A `Dungeon` is a "run" — it starts, is played, and ends. Should it have a `status` field (`IN_PROGRESS`, `COMPLETED`, `ABANDONED`)? What behaviour does this enable?
5. If two players could share a dungeon (co-op), what would need to change in the `Dungeon` model?

---

### Task 1.7 — `Score` dataclass + scoring formula

1. The formula is `floors_reached × kills × item_multiplier`. What is the risk of a multiplicative formula, and how would you guard against a score of zero ruining a good run?
2. Should `Score` be computed inside `GameService`, `ScoreService`, or `SubmitScore` use case? Explain the reasoning.
3. What does it mean for a function to be a "pure function"? Is `ScoreService.compute(dungeon: Dungeon) -> Score` a pure function?
4. `Score` has a `computed_at: datetime`. Where should this value come from — passed in by the caller or generated inside `ScoreService`? Why does this matter for testing?
5. A player exploits a bug and gets `kills = 10_000`. How would you defend against score manipulation at the domain level?

---

### Task 1.8 — `TileType` enum

1. `TileType.WALL` and `TileType.FLOOR` both need to be rendered by the React frontend. The frontend receives the game state as JSON. What does `TileType` serialise to by default in Python, and how would you ensure the frontend gets a predictable string value like `"WALL"`?
2. What is the difference between `IntEnum` and `StrEnum` (Python 3.11+), and which is more appropriate for `TileType`?
3. A tile is passable if it is `FLOOR`, `DOOR` (when open), or `STAIRS`. Should this logic live in `TileType` (as a method), in `Floor`, or in `GameService`?
4. Enums are singletons in Python — `TileType.WALL is TileType.WALL` is always `True`. Why is this useful for game logic compared to strings?
5. How would you extend `TileType` to support `TRAP` and `WATER` without breaking any existing code? What tests would you add?

---

### Task 1.9 — `Action` type union

1. What is a Python `Union` type and how does it differ from a base class hierarchy for modelling actions? Give one advantage of each approach.
2. `ProcessTurn` receives an `Action`. How do you dispatch on the specific action type cleanly in Python 3.10+?
3. A `Move` action has `direction: Direction`. What is the benefit of `Direction` being an enum (`NORTH`, `SOUTH`, `EAST`, `WEST`) rather than a tuple `(dx, dy)`?
4. `Action` objects come from the frontend via WebSocket as JSON. What layer is responsible for converting raw JSON into typed `Action` objects, and what layer should never see raw JSON?
5. What happens in `GameService` if it receives an action type it doesn't recognise? Where should this error be handled, and what should be returned to the client?

---

### Task 1.10 — `IGameRepository` Protocol

1. What is the difference between `typing.Protocol` and `ABC` (Abstract Base Class) in Python? Why is `Protocol` preferred for ports in hexagonal architecture?
2. Write the signature of a `save` method on `IGameRepository` that saves a `Dungeon` and returns the saved entity. Should it return `Dungeon` or `None`? Justify your choice.
3. What does `runtime_checkable` do when added to a Protocol, and when would you need it?
4. `IGameRepository` has a `get(game_id: UUID) -> Dungeon | None`. Why return `None` rather than raising an exception when the game is not found?
5. A new requirement: list all games for a user, paginated. What signature would you add to `IGameRepository`, and how does this follow or break the Interface Segregation Principle?

---

### Task 1.11 — `IScoreRepository` Protocol

1. `IScoreRepository` has `top_n(n: int, period: str) -> list[Score]`. What are the problems with `period: str`, and how would you improve this signature?
2. The leaderboard is read-heavy and write-light. Does `IScoreRepository` need to know about this? Where does this concern belong?
3. What is the Liskov Substitution Principle? Give an example of how a `PostgresScoreRepository` could violate it when implementing `IScoreRepository`.
4. Should `IScoreRepository` expose a `delete(score_id: UUID)` method? When would you include or exclude admin operations from a port interface?
5. Why should the return type of `top_n` be `list[Score]` (domain model) rather than `list[dict]`? What does this enforce?

---

### Task 1.12 — `ICachePort` Protocol

1. `ICachePort` has `get(key: str) -> str | None` and `set(key: str, value: str, ttl: int)`. Why store values as `str` rather than `dict` or `Any`?
2. Who is responsible for serialising and deserialising the `Dungeon` object when storing it in cache — the `ICachePort` adapter, or the use case that calls it?
3. What is a TTL (Time-To-Live) and why is it critical for game session state stored in Redis?
4. A cache `get` returns `None`. What are the two possible reasons for this, and how should the application layer handle each?
5. `ICachePort` is a port. What would a `FakeCachePort` (for unit tests) look like in 5–10 lines of Python?

---

### Task 1.13 — `DungeonGenerator` BSP algorithm

1. What is Binary Space Partitioning (BSP)? Describe the algorithm in plain English in 4–5 sentences.
2. `DungeonGenerator` takes a `seed: int` and is a pure function. Why is the seed important for testability and for the replay feature planned in the backlog?
3. How do you create a seeded random generator in Python without affecting global `random` state?
4. What makes a dungeon floor "valid"? List at least 3 properties your generator should guarantee, and explain how you would assert each in a unit test.
5. BSP tends to produce rectangular rooms. Name one alternative algorithm and describe one trade-off it makes compared to BSP.

---

### Task 1.14 — Unit tests for `DungeonGenerator`

1. What is the difference between a unit test and an integration test? Why are all Phase 1 tests unit tests?
2. `DungeonGenerator` uses randomness. How do you write a deterministic unit test for a function that involves randomness?
3. What is property-based testing? Give one property of `DungeonGenerator` output that would be a good candidate for a property test with `hypothesis`.
4. A test is slow (takes 2 seconds). What are the likely causes in a pure-Python domain test, and how would you fix it?
5. What does code coverage measure, and why is 100% coverage not sufficient to guarantee correctness?

---

### Task 1.15 — `EnemyAI` pathfinding

1. What is Manhattan distance, and why is it the right distance metric for a tile-based grid game (as opposed to Euclidean distance)?
2. `EnemyAI` is a pure function that takes `(enemy: Enemy, player: Player, floor: Floor) -> Action`. Why is a pure function significantly easier to test than a method on `Enemy`?
3. An enemy can't reach the player because a wall blocks the direct path. What approach would you take to make the AI navigate around obstacles? Name the algorithm.
4. What is the risk of running pathfinding for every enemy on every turn as the number of enemies grows? What is the time complexity of A* on a grid?
5. Should `EnemyAI` be part of the domain layer or an adapter? Justify your answer.

---

### Task 1.16 — `GameService.process_turn()`

1. `process_turn` receives an `Action` and a `Dungeon` and returns a new `Dungeon`. Should it mutate the input `Dungeon` or return a new one? What are the trade-offs?
2. What is the order of operations in a turn? Write out the steps (player action → enemy AI → collision detection → state update → result) and explain why order matters.
3. `process_turn` needs a random number generator (for damage variance). How do you pass this in without making `GameService` depend on Python's global `random`?
4. What is a "domain event"? Give an example of a domain event that `process_turn` might emit, and explain why emitting events is better than calling side effects directly.
5. `GameService` has no `__init__` dependencies in a pure hexagonal design — it takes everything as parameters. What are the advantages and disadvantages of this compared to injecting a repository in the constructor?

---

### Task 1.17 — Unit tests for `GameService`

1. What is a "fake" (or "stub") in testing, and how does it differ from a `Mock`? When would you use each?
2. Write out the test cases you need to cover for `process_turn` when the player attacks an enemy. What are the edge cases?
3. `GameService` test uses `FakeGameRepository`. What interface must `FakeGameRepository` satisfy, and how does Python's `Protocol` enforce this?
4. What is the AAA pattern in unit testing? Apply it to a test for `process_turn` when a player descends stairs.
5. A test for `process_turn` fails only sometimes (flaky test). What are the most likely causes, and how do you diagnose and fix each?

---

### Task 1.18 — `ScoreService.compute()`

1. `ScoreService.compute(dungeon: Dungeon) -> Score` — is this a pure function? What makes you certain?
2. The scoring formula uses `item_multiplier`. How do you compute this multiplier from the player's inventory? Where does this logic live?
3. A `Dungeon` that was abandoned (`status = ABANDONED`) should score zero. Should this check live in `ScoreService` or in the `SubmitScore` use case? Justify your answer.
4. What is the risk of `int` overflow when calculating very large scores in Python? Is this actually a concern in Python?
5. How would you make the scoring formula configurable (e.g., different multipliers for different game modes) without changing `ScoreService`?

---

### Task 1.19 — Unit tests for `ScoreService`

1. `ScoreService.compute()` is a pure function with no dependencies. Does it need fake/mock objects in its tests? Why or why not?
2. List 5 distinct test cases for `ScoreService.compute()` that together give you confidence the formula is correct.
3. What is parametrize in pytest, and why is it a good fit for testing `ScoreService` with multiple input scenarios?
4. A score test passes locally but fails in CI. What environment-related causes would you investigate first?
5. What is the purpose of `conftest.py` in pytest, and what would you put in a Phase 1 `conftest.py`?

---

## Phase 1 — Summary quiz (10 questions, need 9/10)

1. Explain hexagonal architecture in your own words. What problem does it solve, and what is the key rule that enforces the architecture?

2. You are reviewing a PR. The developer has put this in `domain/services/game_service.py`:
   ```python
   from sqlalchemy.orm import Session
   def process_turn(session: Session, action: Action) -> Dungeon:
       ...
   ```
   What is wrong, and how do you fix it?

3. What is the difference between `Protocol` and `ABC`? Give a concrete reason why `Protocol` is better for this project's ports.

4. A player dies during `process_turn`. The application needs to: (a) save the final dungeon state to PostgreSQL, (b) trigger a Celery task to recalculate the leaderboard, and (c) return a `GameOver` response to the client. In which layer does each of these happen, and why?

5. Why are domain-layer unit tests in this project always fast and have zero infrastructure dependencies? What specifically ensures this?

6. Describe the BSP dungeon generation algorithm. What properties of the output does it guarantee, and what is one weakness of the approach?

7. A `FakeGameRepository` is used in `GameService` tests. Write out what its `save` method looks like in Python (just the implementation, not the class boilerplate).

8. `process_turn` runs enemy AI for every enemy on every turn. As the floor fills with 50 enemies, what is the performance risk? What is one architectural change that would mitigate it?

9. The `Score` formula: `floors_reached × kills × item_multiplier`. A player reaches floor 5 with 20 kills and 3 items with multipliers [1.5, 2.0, 1.0]. What is the final score? Walk through the calculation.

10. A new developer joins and asks: "Why don't we just use Django ORM models as our domain models? It would save having to map between two sets of models." Give a complete answer explaining the trade-offs.

---
---

## Phase 2 — Persistence adapters

---

### Task 2.1 — `docker-compose.yml`

1. What is Docker Compose and what problem does it solve for local development?
2. What is a named volume in Docker Compose, and why do you use one for the PostgreSQL data directory?
3. What does `depends_on` do in a Compose file, and what does it NOT guarantee?
4. The `postgres` container starts but the application can't connect yet. What is the most common cause, and how do you fix it?
5. How would you add a `pgadmin` service to Compose for local DB inspection, and what port would you expose it on?

---

### Task 2.2 — Alembic setup + initial migration

1. What is Alembic and what is the difference between `alembic revision --autogenerate` and writing a migration manually?
2. What does `alembic upgrade head` do, and what does `alembic downgrade -1` do?
3. Autogenerate compares your SQLAlchemy models to the current database schema. What must be true for autogenerate to work correctly?
4. A migration runs in production and fails halfway through. What is the risk, and what SQL feature protects against partial migrations?
5. Your `users` table needs a new `NOT NULL` column added. What is the safe migration strategy for a table that already has data?

---

### Task 2.3 — SQLAlchemy ORM models

1. What is the difference between a SQLAlchemy ORM model and a domain dataclass? Why keep them separate in this project?
2. What is the N+1 query problem? Give an example where loading `Dungeon` objects in SQLAlchemy could trigger it.
3. What does `relationship(..., lazy="selectin")` do, and when would you choose it over `lazy="joined"`?
4. `Dungeon` has a `Player` in the domain model. How do you represent this in the DB schema? (Foreign key, embedded JSON, or separate table — argue your choice.)
5. What is the purpose of `__tablename__` in a SQLAlchemy model, and does it need to match the Python class name?

---

### Task 2.4 — `PostgresGameRepository`

1. `PostgresGameRepository` implements `IGameRepository`. What specifically must be true for Python's type checker to consider it a valid implementation of the Protocol?
2. `save(dungeon: Dungeon) -> Dungeon` receives a domain object. What are the two main steps in the adapter before data hits the database?
3. What does `async with session.begin()` give you, and what happens if an exception is raised inside the block?
4. What is the `Unit of Work` pattern? Is it already provided by SQLAlchemy, or do you need to implement it yourself?
5. You load a `Dungeon` from PostgreSQL and need to return a domain `Dungeon` dataclass. Write out in pseudocode how you convert between the ORM model and the dataclass.

---

### Task 2.5 — `PostgresScoreRepository`

1. `top_n(n: int, period: ScorePeriod) -> list[Score]` fetches the leaderboard from the database. Write the SQLAlchemy query you would use for the "global all-time top 10".
2. A leaderboard query runs on a table with 10 million rows. What index would you add, and what SQL clause makes the index effective?
3. What is a database transaction isolation level? What level is appropriate for leaderboard reads, and why?
4. `save(score: Score)` must be idempotent — if called twice with the same score, it should not create duplicates. How would you implement this in PostgreSQL?
5. What is the difference between `LIMIT` and `OFFSET` pagination vs keyset (cursor-based) pagination? Which is better for a leaderboard and why?

---

### Task 2.6 — Integration tests for DB repos

1. What is `testcontainers-python` and how does it differ from using a fixed local database for tests?
2. What is a pytest fixture with `scope="session"` vs `scope="function"`, and which scope would you use for the database container? Why?
3. How do you ensure each test starts with a clean database state? Name two approaches and compare them.
4. An integration test passes locally but fails in CI because the container takes 30 seconds to start. What is the standard fix?
5. What is the difference between testing the repository in isolation vs testing the full stack (router → use case → repository)? When would you do each?

---

### Task 2.7 — `RedisCache` implementing `ICachePort`

1. `set(key: str, value: str, ttl: int)`. The `Dungeon` domain object is not a string. Who serialises it before calling `cache.set()`, and what format do you use?
2. What does Redis `SETEX` do, and why use it instead of separate `SET` + `EXPIRE` commands?
3. `redis.asyncio` vs `redis-py` — what is the difference and why does this project use the async version?
4. What is a Redis connection pool, and why does a FastAPI application need one rather than opening a new connection per request?
5. The cache is down. `ICachePort.get()` raises a connection error. How should the application layer handle this gracefully without crashing the game?

---

### Task 2.8 — Integration tests for `RedisCache`

1. What would a minimal integration test for `RedisCache.set()` and `RedisCache.get()` look like? Write the test body in pseudocode.
2. How do you test that a cached value expires correctly after its TTL?
3. Your `RedisCache` integration test passes in isolation but fails when run alongside other tests. What is the most likely cause?
4. What is `fakeredis`, and when would you use it instead of a real Redis container in tests?
5. Should the `RedisCache` integration test use the same Redis instance as the running application? Explain the risks.

---

### Task 2.9 — Supabase Auth setup

1. What is Supabase Auth and what does it give you out of the box compared to rolling your own auth?
2. What is a JWT (JSON Web Token)? What are its three parts, and which part contains the user's identity?
3. What is the difference between the `anon` key and the `service_role` key in Supabase? Which one must never be exposed in frontend code?
4. Supabase issues a JWT with an expiry (`exp` claim). What happens when the token expires, and what must the client do?
5. What is the `aud` (audience) claim in a JWT, and why does Supabase include it?

---

### Task 2.10 — JWT validation FastAPI dependency

1. What is FastAPI's dependency injection system? What is `Depends()` and how does it work?
2. Write the signature of a `get_current_user` dependency function. What does it receive and what does it return?
3. What library do you use to decode and verify a JWT in Python, and what three things must you verify?
4. `get_current_user` raises `HTTPException(status_code=401)`. What HTTP header should the response include per the HTTP spec?
5. What is the difference between authentication and authorisation? Give an example of each in the context of this game's API.

---

### Task 2.11 — Supabase Storage bucket setup

1. What is object storage, and how does it differ from storing files in a PostgreSQL `BYTEA` column?
2. What is a "bucket" in Supabase Storage? What is the difference between a public and a private bucket?
3. How does a FastAPI route upload a file to Supabase Storage? Describe the flow in 3–4 steps.
4. What is a pre-signed URL, and when would you use one instead of proxying file downloads through your API?
5. A save file in Supabase Storage has a key like `saves/{user_id}/{game_id}.json`. What benefits does this key structure give you?

---

## Phase 2 — Summary quiz (10 questions, need 9/10)

1. Explain the repository pattern. Why does `PostgresGameRepository` implement `IGameRepository`, and what would change if you swapped to MongoDB tomorrow?

2. What is the N+1 query problem? Write a SQLAlchemy example that causes it and show how to fix it.

3. A `Dungeon` domain model has a `List[Floor]` which each have a `List[Enemy]`. Design the PostgreSQL schema (table names, columns, foreign keys) to store this structure. Describe trade-offs vs storing the whole `Dungeon` as JSON.

4. Alembic autogenerate creates an empty migration. What are two reasons this might happen?

5. Redis goes down in production. The application is currently loading active game state from Redis on every WebSocket message. Describe your fallback strategy and what you would log.

6. Describe what happens step-by-step when a request comes in with a JWT Bearer token and how `get_current_user` processes it.

7. What is the difference between a unit test, an integration test, and an end-to-end test? Give one example of each from Phase 2.

8. Why does this project keep domain dataclasses separate from SQLAlchemy ORM models? Give two concrete problems that would arise if you merged them.

9. A player's score is saved twice due to a network retry. How would you make `PostgresScoreRepository.save()` idempotent? Write the SQL or describe the approach.

10. What is connection pooling? Configure `asyncpg` connection pool settings for a FastAPI app that receives 200 concurrent requests. What values would you set and why?

---
---

## Phase 3 — Application use cases + API

---

### Task 3.1 — `StartGame` use case

1. What is a use case in hexagonal architecture? How is it different from a domain service?
2. `StartGame` creates a `Dungeon`, saves it to the DB, and caches the first floor in Redis. Write out the steps in order and explain which layer each step belongs to.
3. Should `StartGame` accept a `user_id: UUID` directly or a `Player` domain object? Why?
4. What is the `Command` pattern, and does `StartGame` follow it?
5. `StartGame` calls both `IGameRepository.save()` and `ICachePort.set()`. If the cache write fails after the DB save, what is the state of the system? How would you handle this?

---

### Task 3.2 — `ProcessTurn` use case

1. `ProcessTurn` loads state from Redis, not from PostgreSQL. Why? What does this imply about the relationship between the cache and the database?
2. Two requests arrive simultaneously for the same session (e.g., the client sent two moves quickly). What is the race condition risk, and how would you protect against it?
3. What does `ProcessTurn` return to the WebSocket handler? Describe the structure of the response payload.
4. Where does `ProcessTurn` persist state after a turn — only Redis, only PostgreSQL, or both? Justify your answer.
5. `ProcessTurn` detects the player has died. What does it do differently compared to a normal turn?

---

### Task 3.3 — `SubmitScore` use case

1. `SubmitScore` calls `ScoreService.compute()` and then saves the result. Is this correct? What happens if `compute()` is called with a dungeon that isn't finished?
2. After saving the score, `SubmitScore` triggers a Celery task. Why trigger an async task instead of rebuilding the leaderboard synchronously inside the use case?
3. How does `SubmitScore` pass the `Dungeon` to the Celery task? (You can't pass the full object — what do you pass instead?)
4. `SubmitScore` should clean up the active game state from Redis. When exactly should this happen relative to the DB save?
5. What does "idempotent" mean in the context of `SubmitScore`? How would you make it idempotent?

---

### Task 3.4 — FastAPI app setup

1. What is the FastAPI `lifespan` context manager used for? Give two resources you would initialise and clean up there.
2. What does `CORSMiddleware` do and why does this project need it?
3. What is the difference between `APIRouter` and including all routes directly in the `FastAPI()` app object?
4. What is `Depends()` used for in the context of app-wide dependencies like database sessions?
5. What is the difference between `@app.on_event("startup")` (deprecated) and the `lifespan` approach? Why was the change made?

---

### Task 3.5 — Auth endpoints

1. `POST /auth/register` receives `email` and `password`. These go to Supabase, not your database. What does your backend return to the client?
2. What is the difference between `access_token` and `refresh_token`? When should the client use each?
3. Should your FastAPI backend store passwords? Justify your answer.
4. What HTTP status code do you return for a failed login due to wrong password, and why is `401` correct while `403` is not?
5. What is the purpose of the `Authorization: Bearer <token>` header pattern?

---

### Task 3.6–3.8 — Game REST endpoints

1. `POST /game/start` creates a game. What HTTP status code should it return on success — `200 OK` or `201 Created` — and what should the response body contain?
2. `GET /game/{id}` should return 404 if the game doesn't exist. Where in the stack does this check happen — the router, the use case, or the repository?
3. `POST /game/{id}/abandon` ends the run. What state changes are required in DB and Redis, and in what order?
4. What is idempotency? Is `POST /game/{id}/abandon` idempotent? Should it be?
5. A user requests `GET /game/{id}` for a game that belongs to a different user. What HTTP status code do you return, and what check prevents this?

---

### Task 3.9 — WebSocket turn loop

1. What is the lifecycle of a WebSocket connection in Starlette/FastAPI? List the stages from connection request to close.
2. The client sends `{"action": "move", "direction": "NORTH"}`. Walk through every step from receiving this message to sending the response back.
3. What happens to the WebSocket connection if `process_turn` raises an unhandled exception? What should your handler do?
4. How do you authenticate a WebSocket connection? WebSockets don't support custom headers from the browser — what is the standard workaround?
5. A player closes the browser tab. What happens to the WebSocket on the server side, and how do you detect and clean up a broken connection?

---

### Task 3.10–3.12 — Leaderboard endpoints

1. `GET /leaderboard/global` is served from Redis cache. What is the cache key, and how do you handle a cache miss?
2. What is a cache stampede, and how does it occur on the leaderboard endpoint if Redis is cold and 1,000 requests arrive at once?
3. `GET /leaderboard/me` requires authentication. How does your router know the current user's ID without querying the DB?
4. Should the leaderboard endpoint be paginated? Argue both sides for a top-100 list.
5. The leaderboard data in Redis is 5 minutes stale. A new high score was just submitted. When will the cache update?

---

### Task 3.13 — Pydantic v2 schemas

1. What is the difference between a Pydantic model and a SQLAlchemy model? What is each used for?
2. What does `model_config = ConfigDict(from_attributes=True)` do in a Pydantic v2 model?
3. Pydantic v2 uses `model_validator` and `field_validator`. What is the difference, and give an example where each is appropriate?
4. What is the difference between `BaseModel` serialisation (`.model_dump()`) and FastAPI's automatic response serialisation? When would you call `.model_dump()` manually?
5. A `PlayerResponse` schema should not expose the player's email or internal DB id. How do you control which fields are included/excluded?

---

### Task 3.14–3.15 — Tests

1. What is `TestClient` in FastAPI/Starlette? How does it differ from a real HTTP client in tests?
2. How do you override a dependency (e.g., `get_current_user`) in FastAPI integration tests?
3. What library do you use to test WebSocket connections in pytest, and what does an async WebSocket test look like structurally?
4. What is `pytest.mark.asyncio` and when is it required?
5. Should integration tests for the API use a real database or a fake repository? What is the trade-off?

---

## Phase 3 — Summary quiz (10 questions, need 9/10)

1. Draw (in text) the full call stack when a WebSocket message arrives with `{"action": "attack"}`. Start from the WebSocket handler and go all the way down to the domain, then back up.

2. What is the difference between a use case and a domain service? Use `ProcessTurn` and `GameService` as examples.

3. FastAPI uses dependency injection heavily. Explain `Depends()` and give two examples from this project where it is used.

4. A race condition exists in `ProcessTurn` if the client sends two moves quickly. Describe the race, and describe two ways to prevent it at the application level.

5. What is Pydantic v2's `model_validator(mode='before')` vs `mode='after'`? Give a concrete example of each from this project.

6. `GET /leaderboard/global` must respond in < 50ms. Trace every layer the request touches and explain what makes each layer fast enough.

7. What does `lifespan` in FastAPI replace, and why is it preferred? What would you put in the startup and shutdown phases for this project?

8. A player submits their score at the exact same time as the weekly Celery reset runs. What is the worst-case outcome, and how would you prevent it?

9. What HTTP status codes apply to each of these scenarios: (a) game not found, (b) valid request but user not authenticated, (c) authenticated but accessing another user's game, (d) server DB crash mid-request.

10. Describe the full WebSocket authentication flow — from the client opening a connection to the server confirming the user's identity — without using custom headers.

---
---

## Phase 4 — Celery workers

---

### Task 4.1 — Celery app setup

1. What is Celery and what problem does it solve that you can't solve with Python's `asyncio`?
2. What is the difference between a Celery broker and a Celery result backend? What does each store?
3. Why use Redis as both broker and result backend in this project rather than RabbitMQ?
4. What is a Celery worker and how does it differ from the FastAPI app process?
5. What is `task_serializer = "json"` and why should you never use `"pickle"` in a production Celery setup?

---

### Task 4.2 — `score_recalc` task

1. The `score_recalc` task rebuilds the leaderboard. What does "rebuild" mean concretely — what does it read and what does it write?
2. Why is `score_recalc` triggered by `SubmitScore` as an async task rather than being called synchronously inline?
3. What does `@app.task(bind=True)` give you access to inside the task function?
4. What is task idempotency and why is it critical for `score_recalc`? What happens if it runs twice?
5. How would you implement retry logic on `score_recalc` if the Redis write fails? Write the decorator.

---

### Task 4.3 — `map_generation` task

1. `map_generation` pre-generates floor N+1 while the player is on floor N. Where does the generated `Floor` get stored, and under what key?
2. What is the risk of running `DungeonGenerator` (BSP) synchronously in the FastAPI request handler for deep floors? Why does this justify a Celery task?
3. How does the FastAPI request know when the pre-generated floor is ready? Describe the flow.
4. What happens to the pre-generated floor data if the player dies before descending? When should it be cleaned up?
5. `map_generation` is called with `game_id` and `floor_index`. How do you make sure only one task per `(game_id, floor_index)` runs, even if triggered twice?

---

### Task 4.4 — `weekly_leaderboard_reset` task

1. What does the weekly reset need to do? List the steps in order (archive → wipe → notify?).
2. `weekly_leaderboard_reset` deletes score records. What is the risk if it runs while `score_recalc` is also running?
3. How do you make `weekly_leaderboard_reset` safe to run even if it crashes halfway through and is retried?
4. Should this task email users their weekly ranking? Should that logic be in this task or a separate task?
5. What is Celery Beat and how does it differ from cron? What advantage does it have for a containerised environment?

---

### Task 4.5 — Celery Beat schedule

1. What is the `CELERYBEAT_SCHEDULE` configuration? Write a schedule entry that runs `weekly_leaderboard_reset` every Monday at midnight UTC.
2. Can two Celery Beat instances run simultaneously for the same schedule? What would happen?
3. What is the difference between `crontab` and `timedelta` schedule types in Celery Beat?
4. How does Celery Beat persist its schedule state, and what happens if the Beat container restarts?
5. You want the weekly reset to run at midnight in Poland's timezone (CET/CEST). How do you configure this in Celery Beat?

---

### Tasks 4.6–4.7 — Docker Compose + testing

1. Add a Celery worker service to `docker-compose.yml`. What command does it run, and what does it share with the FastAPI service?
2. How do you test that `SubmitScore` correctly enqueues the `score_recalc` task without running a real Celery worker?
3. What is `task_always_eager` in Celery, and when would you enable it in tests?
4. What is the difference between `apply_async()` and `delay()` in Celery?
5. How do you run a Celery task synchronously in a test without a broker?

---

## Phase 4 — Summary quiz (10 questions, need 9/10)

1. What is the difference between Celery, the Celery worker, and Celery Beat? Draw a simple diagram in text showing how they interact.

2. `score_recalc` must be idempotent. Explain what "idempotent" means and describe how you implement it for a leaderboard rebuild.

3. A Celery task fails. What are the three outcomes depending on your retry configuration? Write a `@app.task` decorator that retries up to 3 times with exponential backoff.

4. `weekly_leaderboard_reset` runs while `score_recalc` is also running. Describe the race condition and one way to prevent it using Redis.

5. What is `task_serializer = "json"` and why is `"pickle"` dangerous in production?

6. A Celery worker crashes mid-task. What happens to the task message in the broker? What is task acknowledgement and when does it happen by default?

7. You need to run the weekly reset every Monday at midnight Warsaw time. Write the `crontab` configuration and explain how timezone handling works in Celery Beat.

8. `map_generation` is triggered when a player descends to floor 5 (to pre-generate floor 6). Describe the entire flow from the WebSocket handler triggering the task to the player receiving floor 6.

9. How do you test a Celery task in pytest without a running broker? Name two approaches and explain the trade-offs.

10. `score_recalc` reads 10,000 score rows from PostgreSQL to rebuild the leaderboard. This is slow. Describe two optimisation strategies at the query or cache level.

---
---

## Phase 5 — React frontend

---

### Task 5.1 — Vite + React setup

1. What is Vite and how does it differ from Create React App in development mode?
2. What is `tsconfig.json` and should you use TypeScript for this project? Give one reason for and one reason against.
3. What is ESLint in the context of a React project and what does it catch?
4. What is the purpose of `vite.config.ts`, and what would you configure there for this project (e.g., proxy)?
5. What is tree-shaking and why does Vite's production build apply it?

---

### Task 5.2 — Pixel tile set design

1. What is a sprite sheet and why use one instead of individual image files for tiles?
2. What does "16×16 tiles" mean for canvas rendering? How does this translate to actual pixel size on a modern 4K screen?
3. What is `imageSmoothingEnabled = false` on a canvas context, and why is it essential for pixel art?
4. What colour format does a GBA-style 4-colour palette use, and why does limiting colours give pixel art a retro feel?
5. How would you represent the tile set in the frontend codebase — as a single image file, individual PNGs, or an SVG sprite? Justify your choice.

---

### Task 5.3 — Canvas renderer

1. What is the difference between `canvas` and SVG for game rendering? Why is `canvas` the right choice here?
2. `drawImage(spriteSheet, sx, sy, sWidth, sHeight, dx, dy, dWidth, dHeight)` — what do each of the coordinates represent?
3. How do you clear the canvas between frames? What happens if you don't?
4. The `Floor` arrives from the backend as a JSON grid. What is the render loop — how do you iterate the grid and draw tiles?
5. What is `requestAnimationFrame` and why use it instead of `setInterval` for game rendering?

---

### Task 5.4–5.5 — Sprites and animation

1. What is frame-based animation, and how would you implement a 4-frame walking animation for the player sprite?
2. What is `performance.now()` and how do you use it to make animations frame-rate independent?
3. Why should game animation state (current frame, last frame time) live in a React `ref` rather than `state`?
4. How do you animate an enemy moving from tile (3,4) to (3,5) smoothly rather than teleporting?
5. What is a "sprite atlas" and how does it reduce HTTP requests compared to individual sprite images?

---

### Task 5.6 — `useGameSocket` hook

1. What is a custom React hook and what rules must it follow?
2. Why should the WebSocket connection be managed inside a `useEffect` with a cleanup function?
3. The WebSocket receives a game state update. How do you update React state to trigger a re-render of the game canvas?
4. What is `useRef` and when would you use it inside `useGameSocket` rather than `useState`?
5. `useGameSocket` exposes `sendAction(action)`. How do you prevent the function reference from changing on every render (causing unnecessary effect re-runs)?

---

### Task 5.7 — Keyboard input handler

1. What is the difference between `keydown` and `keyup` events? Which do you use for movement input in a turn-based game?
2. Why attach the keyboard listener to `document` rather than to the canvas element?
3. How do you prevent keyboard input from triggering during text input (e.g., the login form)?
4. What is `event.preventDefault()` and when should you call it for game keyboard events?
5. A player presses WASD rapidly. How do you prevent queuing multiple actions before the server responds to the first?

---

### Task 5.8–5.9 — HUD and game over screen

1. Should the HUD be rendered on the canvas or as HTML elements over the canvas? What are the trade-offs?
2. `HP` is a value from 0 to 100. Describe how you would render a pixel-art-style HP bar on the canvas.
3. What React state shape would you use to store the current game state received from the WebSocket?
4. The game over screen appears when `event.type === "game_over"`. Where does this transition logic live — in `useGameSocket`, a state machine, or a component?
5. What is a "flash of unstyled content" (FOUC) and how do you prevent it when transitioning from the game screen to the game over screen?

---

### Task 5.10–5.11 — Leaderboard and auth screens

1. `GET /leaderboard/global` is a REST endpoint. What React pattern do you use to fetch and display this data, and how do you handle loading and error states?
2. What is `SWR` or `React Query`, and what problem do they solve compared to raw `useEffect` + `fetch`?
3. The auth screen stores the JWT in the browser. Where should you store it — `localStorage`, `sessionStorage`, or an in-memory variable — and what are the security trade-offs of each?
4. What is an XSS (Cross-Site Scripting) attack, and how does storing the JWT in `localStorage` make it vulnerable?
5. What is a `PrivateRoute` (or route guard) in React and how would you implement one?

---

### Task 5.12 — Supabase JWT auth flow

1. Describe the full auth flow from the user clicking "Login" to being able to send authenticated WebSocket messages.
2. What is `supabase.auth.getSession()` and when would you call it?
3. The JWT expires while the user is mid-game. What should happen? How does your frontend detect and handle token expiry?
4. What is `supabase.auth.onAuthStateChange()` and when is it useful?
5. How do you attach the JWT to a WebSocket connection (browsers don't support custom headers)?

---

## Phase 5 — Summary quiz (10 questions, need 9/10)

1. Explain the React rendering model. When does a component re-render, and how do you prevent unnecessary re-renders in a game that receives WebSocket updates 10× per second?

2. What is the difference between `useState`, `useRef`, and `useReducer`? Give an example use case for each from this game.

3. Describe how you would implement the complete WebSocket connection lifecycle in a custom hook: connect on mount, send actions, receive events, reconnect on drop, disconnect on unmount.

4. Canvas vs HTML for the game HUD — argue both sides and give your final decision.

5. A player is on a leaderboard with 10,000 entries. How would you implement infinite scroll / pagination in the React component? What API changes would be needed?

6. The JWT expires mid-game. Describe the exact sequence of events: what the frontend detects, what it does, and how the game continues without the player losing progress.

7. What is `useCallback` and `useMemo`? Show one concrete example from `useGameSocket` where each would prevent a performance problem.

8. How does pixel-art rendering differ from regular web rendering? What two canvas settings are essential for crisp pixel art?

9. The game receives a WebSocket message every turn. Describe the data flow from WebSocket event → React state update → canvas re-render. What triggers the canvas draw?

10. What is XSS and CSRF? Which one is a risk for this game's JWT handling, and what is the mitigation?

---
---

## Phase 6 — Docker + AWS deploy

---

### Task 6.1–6.2 — Dockerfiles

1. What is a multi-stage Docker build and why does it produce a smaller final image?
2. Why copy `requirements.txt` before copying the rest of the source code? What caching benefit does this give?
3. What is the difference between `CMD` and `ENTRYPOINT` in a Dockerfile?
4. The Celery worker uses the same Docker image as the FastAPI app but a different `CMD`. What does the Celery CMD look like?
5. What does `--no-cache-dir` do in `pip install`, and why use it in a Docker build?

---

### Task 6.3 — `docker-compose.prod.yml`

1. What changes between `docker-compose.yml` (dev) and `docker-compose.prod.yml`? List at least 4 differences.
2. What is `gunicorn` and why use it in production instead of `uvicorn` alone?
3. What is the recommended `gunicorn` command for a FastAPI/ASGI app, and how many workers should you configure?
4. What is a Docker health check and how would you add one to the FastAPI service?
5. What does `restart: always` do in a Compose file, and what are its limitations?

---

### Task 6.4 — GitHub Actions CI

1. What is a GitHub Actions workflow and what triggers it? What file structure does it use?
2. What is the difference between a job and a step in a workflow?
3. What does `actions/cache` help with in a Python CI workflow?
4. What is `mypy` and why would you add it to CI alongside `pytest`?
5. What is the difference between `ruff` and `black` as linting/formatting tools?

---

### Task 6.5 — AWS VPC setup

1. What is a VPC (Virtual Private Cloud) and why does every production AWS deployment need one?
2. What is the difference between a public subnet and a private subnet in AWS?
3. What is a NAT Gateway and when is it required?
4. What is a Security Group and how does it differ from a Network ACL?
5. Your FastAPI ECS task needs to reach the RDS database. Describe the security group rules required.

---

### Task 6.6–6.7 — RDS + ElastiCache

1. What is the difference between RDS PostgreSQL and a self-managed PostgreSQL on EC2?
2. What is Multi-AZ in RDS and what failure does it protect against?
3. What is an RDS parameter group and give one setting you would change for a game workload?
4. What is ElastiCache Redis and how does it differ from running Redis in a Docker container?
5. What is a Redis cluster mode and when would you enable it?

---

### Task 6.8–6.9 — ECS Fargate + ALB

1. What is ECS Fargate and how does it differ from ECS on EC2?
2. What is a Task Definition in ECS, and what does it specify?
3. What is the difference between an ECS Service and a standalone ECS Task?
4. What is an ALB (Application Load Balancer) and what Layer does it operate on?
5. How does the ALB route WebSocket upgrade requests to ECS tasks? What must be configured?

---

### Task 6.10–6.11 — CD + HTTPS

1. What does a GitHub Actions CD pipeline for ECS look like? List the steps from code merge to running container.
2. What is ECR (Elastic Container Registry) and why use it over Docker Hub for AWS deployments?
3. What is ACM (AWS Certificate Manager) and how do you attach a certificate to an ALB?
4. What is Route 53 and what record type would you create to point `hexcrawl.com` at the ALB?
5. What is the difference between HTTPS termination at the ALB vs end-to-end TLS?

---

## Phase 6 — Summary quiz (10 questions, need 9/10)

1. Describe the full AWS architecture for HexCrawl in production. Name every AWS service used and explain its role.

2. What is a multi-stage Docker build? Write out a `Dockerfile` sketch (not every line — just the stages) for the FastAPI app.

3. A deployment fails and the new ECS task crashes on startup. How do you investigate? What AWS tools do you use?

4. What is a VPC, and why do you place RDS and ElastiCache in private subnets?

5. GitHub Actions triggers on merge to `main`. What are the steps in your CD pipeline from push to running ECS task?

6. What is the difference between RDS Multi-AZ and a Read Replica? When would you use each?

7. The ALB health check is failing. What are the three most common causes, and how do you diagnose each?

8. Your ECS task needs the `DATABASE_URL` secret at runtime. Describe two ways to inject it, and explain why environment variables in the task definition are not the secure choice.

9. What is the difference between horizontal and vertical scaling? How does ECS Fargate auto-scaling implement horizontal scaling for the HexCrawl API?

10. WebSocket connections drop when ECS scales in (removes a task). Describe this problem and two ways to mitigate it.
