# HexCrawl — CLAUDE.md

> AI assistant context file. Read this before touching any code.
> Last updated: 2026-04

---

## What is this project?

HexCrawl is a browser-based, turn-based dungeon crawler (roguelike) with a global leaderboard.
Players descend procedurally generated floors, fight enemies, collect items, and submit a score on death.

The backend is the portfolio centrepiece — built with **strict hexagonal (ports & adapters) architecture**
in FastAPI. Every domain service is framework-agnostic and fully unit-testable in isolation.

**Stack at a glance**

| Layer        | Technology                                      |
|--------------|-------------------------------------------------|
| Frontend     | React (Vite), HTML5 Canvas (pixel / GBA-style)  |
| API          | FastAPI (async), WebSockets for turn loop        |
| Domain       | Pure Python — zero framework imports            |
| Auth         | Supabase Auth (JWT), FastAPI dependency inject   |
| DB           | PostgreSQL via SQLAlchemy (async + asyncpg)      |
| Cache        | Redis (active game state, leaderboard cache)     |
| Workers      | Celery + Celery Beat (score recalc, weekly reset)|
| Storage      | Supabase Storage (save files, avatars)           |
| Infra        | Docker Compose (local), AWS ECS (prod target)    |

---

## Architecture — Hexagonal / Ports & Adapters

The **golden rule**: nothing inside `domain/` or `application/` may import from
FastAPI, SQLAlchemy, Redis, Celery, or any other framework. Domain logic depends
only on abstract `Protocol` interfaces defined in `domain/ports/`.

```
src/
├── domain/                  # Pure Python. No framework deps. Ever.
│   ├── models/              # Dataclasses: Player, Dungeon, Floor, Enemy, Item, Score
│   ├── services/            # GameService, ScoreService, DungeonGenerator
│   └── ports/               # Protocol interfaces: IGameRepo, IScoreRepo, ICachePort
│
├── application/             # Use cases. Orchestrates domain services.
│   ├── start_game.py        # CreateGame use case
│   ├── process_turn.py      # ProcessTurn use case
│   └── submit_score.py      # SubmitScore use case
│
├── adapters/                # Concrete implementations of ports.
│   ├── db/                  # SQLAlchemy repos implementing IGameRepo, IScoreRepo
│   ├── cache/               # RedisCache implementing ICachePort
│   └── tasks/               # Celery tasks (score_recalc, map_gen, weekly_reset)
│
├── entrypoints/             # FastAPI routers. Depend on application layer only.
│   ├── http/                # REST: /auth /game /leaderboard
│   └── ws/                  # WebSocket: /ws/game/{session_id}
│
└── config.py                # Pydantic Settings, loaded from env
```

### Dependency direction (read carefully)

```
entrypoints → application → domain ← adapters
                                  ↑
                             ports (Protocols)
```

Adapters implement ports. Domain defines ports. Domain never knows adapters exist.

---

## Key Domain Concepts

- **Dungeon** — a run instance. Has floors, current floor index, seed.
- **Floor** — a 2D grid of tiles. Generated procedurally (BSP algorithm).
- **Player** — position, HP, inventory, stats.
- **Enemy** — position, HP, behaviour type (melee / ranged / boss).
- **Turn** — a player action (move, attack, use item, descend stairs). Results in a new game state.
- **Score** — computed on game over: floors reached × enemies killed × item multiplier.
- **Leaderboard** — global all-time + weekly (reset by Celery Beat every Monday 00:00 UTC).

---

## WebSocket turn loop

```
Client  ──→  WS /ws/game/{session_id}  ──→  process_turn use case
                                             ├── validate action
                                             ├── run enemy AI
                                             ├── update state
                                             └── persist to Redis

Server  ──→  push GameStateEvent back to client (JSON)
```

Active game state lives in Redis (TTL 2h). Persisted to PostgreSQL only on:
- game over
- floor descent (checkpoint)
- explicit save

---

## API surface (planned)

| Method | Path                        | Description                  |
|--------|-----------------------------|------------------------------|
| POST   | /auth/register              | Create account               |
| POST   | /auth/login                 | Get JWT                      |
| POST   | /game/start                 | Create new dungeon run       |
| GET    | /game/{id}                  | Fetch saved game state       |
| WS     | /ws/game/{session_id}       | Real-time turn processing    |
| POST   | /game/{id}/abandon          | End run without scoring      |
| GET    | /leaderboard/global         | All-time top 100             |
| GET    | /leaderboard/weekly         | This week's top 100          |
| GET    | /leaderboard/me             | Current user's best scores   |

---

## Celery tasks

| Task                  | Trigger                  | Description                              |
|-----------------------|--------------------------|------------------------------------------|
| `score_recalc`        | After every game over    | Async leaderboard rebuild (non-blocking) |
| `map_generation`      | On floor descent (deep)  | Offload heavy BSP gen for floors 10+     |
| `weekly_leaderboard`  | Celery Beat — Mon 00:00  | Archive + reset weekly scores            |

---

## Code conventions

- **Python 3.12+** — use `match` statements for action dispatching, `TypeAlias` for clarity.
- **Type hints everywhere.** No `Any` in domain or application layers.
- **Pydantic v2** for all API schemas. Domain models are plain dataclasses.
- **Tests first for domain and application layers.** Use `pytest` + `pytest-asyncio`.
- **No print statements.** Use `structlog` for all logging.
- **Async all the way down** in adapters and entrypoints (`asyncpg`, `redis.asyncio`).
- Branch naming: `feat/`, `fix/`, `chore/` prefixes.
- Commit style: Conventional Commits (`feat: add BSP dungeon generator`).

---

## Repo layout (top level)

- `src/` — backend Python (see hexagonal layout above).
- `tests/` — pytest tree (`unit/`, `integration/`, `e2e/`).
- `frontend/` — React + Vite app. Its own `package.json`, `pnpm-lock.yaml`, `tsconfig.json`.
- `alembic/` — migrations.
- `requirements/` — pinned pip requirements (`base.txt`, `dev.txt`, `prod.txt`).
- `.github/workflows/` — CI pipelines (see below).
- `BOARD.md` / `QUIZZES.md` / `QUESTIONS.md` — project state. Not code.

---

## Tooling & CI

### Python toolchain
- **Lint:** `ruff check src tests`
- **Format:** `black src tests` (run `black --check` in CI)
- **Types:** `mypy src` — strict enough that `Any` in `domain/` / `application/` fails.
- **Tests:** `pytest` with `pytest-asyncio` and `pytest-cov`. Coverage gate: **≥ 80%** (`--cov-fail-under=80`).
- **Migrations:** `alembic upgrade head`, `alembic check` in CI if available.

### Frontend toolchain
- **Package manager:** `pnpm` (version 9). Lockfile: `frontend/pnpm-lock.yaml`.
- **Lint:** `pnpm lint` (ESLint).
- **Format:** `pnpm exec prettier --check .`
- **Types:** `pnpm tsc --noEmit`.
- **Tests:** `pnpm test -- --run --coverage` (Vitest).
- **Build:** `pnpm build` (Vite).

### GitHub Actions pipelines

Workflows live in `.github/workflows/`. Each has a `preflight` job that skips downstream jobs when the relevant source tree doesn't exist yet — so merging the pipelines before the code is safe.

| Workflow | File | Triggers | Jobs |
|----------|------|----------|------|
| Python CI | `python.yml` | push/PR to `main` | `lint` (ruff + black), `typecheck` (mypy), `test` (pytest + coverage, Postgres + Redis services) |
| Frontend CI | `frontend.yml` | push/PR to `main` | `lint-and-format` (ESLint + Prettier), `typecheck` (tsc), `test` (Vitest + coverage), `build` (Vite) |

Dependabot (`.github/dependabot.yml`) updates pip, npm, GitHub Actions, and Docker weekly.

### Definition of "green CI"
A PR is mergeable when:
1. All Python jobs green (or skipped via preflight).
2. All frontend jobs green (or skipped via preflight).
3. Coverage ≥ 80% on the touched tier.
4. No `mypy` errors in `src/`.
5. Hexagonal boundary rule holds (enforced socially via code review + `/audit`; an automated import-linter check is on the backlog).

---

## Local dev setup

```bash
# 1. Clone and create venv
python -m venv .venv && source .venv/bin/activate

# 2. Install deps
pip install -r requirements/dev.txt

# 3. Start infra
docker compose up -d postgres redis

# 4. Run migrations
alembic upgrade head

# 5. Start API
uvicorn src.entrypoints.http.main:app --reload

# 6. Start Celery worker (separate terminal)
celery -A src.adapters.tasks.celery_app worker --loglevel=info

# 7. Start Celery Beat (separate terminal)
celery -A src.adapters.tasks.celery_app beat --loglevel=info
```

### Key env vars (copy `.env.example` → `.env`)

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/hexcrawl
REDIS_URL=redis://localhost:6379/0
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
JWT_SECRET=
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

---

## Testing strategy

```
tests/
├── unit/
│   ├── domain/          # Pure logic — no mocks needed, just dataclasses
│   └── application/     # Use cases — mock ports with simple fakes
├── integration/
│   ├── adapters/        # Test real DB / Redis with testcontainers
│   └── entrypoints/     # TestClient + fake repos
└── e2e/
    └── ws/              # WebSocket turn loop end-to-end
```

Run all: `pytest --cov=src --cov-report=term-missing`

Domain unit tests should be instant (< 1s). No I/O.

---

## Collaborators

| Name       | Role            | GitHub  |
|------------|-----------------|---------|
| Krzysztof  | Lead dev        | @...    |
| —          | TBD             |         |

If adding a collaborator: assign tasks in BOARD.md, use PR reviews for adapter/entrypoint changes.
Domain changes must be reviewed by at least one person — this is where correctness lives.

---

## Useful references

- [FastAPI WebSockets docs](https://fastapi.tiangolo.com/advanced/websockets/)
- [Hexagonal architecture (Alistair Cockburn)](https://alistair.cockburn.us/hexagonal-architecture/)
- [Celery docs](https://docs.celeryq.dev/)
- [SQLAlchemy async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [BSP dungeon generation](http://www.roguebasin.com/index.php/Basic_BSP_Dungeon_generation)
