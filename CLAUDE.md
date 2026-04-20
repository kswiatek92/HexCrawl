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

## The real goal: learning

HexCrawl is a vehicle for learning, not just a shipping target. Production quality matters — I want a portfolio piece I'm proud of — but if I finish the project without understanding how it works, I've failed even if the app runs perfectly.

Treat every interaction as a teaching opportunity, not a task-completion opportunity. **When in doubt: slow me down, don't speed me up.** The operational rules for this live in *How to help me learn* near the end of this file — read them.

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
- `pyproject.toml` — Python project metadata, runtime deps (`[project]`), dev deps (`[dependency-groups] dev`), and tool config (ruff, black, mypy, pytest, coverage).
- `uv.lock` — resolved lockfile managed by [uv](https://docs.astral.sh/uv/). Committed; CI installs with `uv sync --all-groups --frozen`.
- `.python-version` — pins the interpreter (3.12) for `uv sync`.
- `.github/workflows/` — CI pipelines (see below).
- **Learning artifacts** (see *How to help me learn*): `BOARD.md`, `QUIZZES.md`, `QUESTIONS.md`, `PREDICTIONS.md`, `DECISIONS.md`, `BUGS.md`. Not code — but treat them as first-class project state.

---

## Tooling & CI

### Python toolchain
- **Package / env manager:** [`uv`](https://docs.astral.sh/uv/). Runtime deps live in `pyproject.toml` under `[project]`; dev tools under `[dependency-groups] dev`. Install everything with `uv sync --all-groups` (or `--frozen` in CI).
- **Lint:** `uv run ruff check src tests`
- **Format:** `uv run black src tests` (CI runs `uv run black --check`)
- **Types:** `uv run mypy src` — strict enough that `Any` in `domain/` / `application/` fails.
- **Tests:** `uv run pytest` with `pytest-asyncio` and `pytest-cov`. Coverage gate: **≥ 80%** (`--cov-fail-under=80`).
- **Migrations:** `uv run alembic upgrade head`, `uv run alembic check` in CI if available.

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

Dependabot (`.github/dependabot.yml`) updates uv (Python), npm (frontend), GitHub Actions, and Docker weekly.

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
# 1. Install uv (once) — https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Sync runtime + dev deps into .venv/ (reads pyproject.toml + uv.lock)
uv sync --all-groups

# 3. Start infra
docker compose up -d postgres redis

# 4. Run migrations
uv run alembic upgrade head

# 5. Start API
uv run uvicorn src.entrypoints.http.main:app --reload

# 6. Start Celery worker (separate terminal)
uv run celery -A src.adapters.tasks.celery_app worker --loglevel=info

# 7. Start Celery Beat (separate terminal)
uv run celery -A src.adapters.tasks.celery_app beat --loglevel=info
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

## How to help me learn

These rules override the "just implement the feature" default. If I appear to be skipping them repeatedly, call it out — that pattern is itself a learning signal.

### Before writing non-trivial code
If I ask you to build a feature, module, or anything beyond ~20 lines of mechanical code, **pause and ask me to predict first**:
- What do I think the rough approach is?
- Which files/functions will change?
- What's the trickiest part likely to be?

Only proceed after I've written my prediction (in `PREDICTIONS.md` or inline in chat). If I say "skip prediction," proceed but note it in your reply — so if I do it too often, I notice the pattern.

### After generating code
Before I move on, pick **one** of these and ask me — rotate, don't repeat the same one every turn:
1. "Why this approach over [a plausible alternative]?"
2. "What are the failure modes and edge cases?"
3. "Can you explain back what [specific block] is doing?"
4. "Want a minimal toy version that isolates the core pattern?"

### When introducing an unfamiliar concept
If the code uses a pattern, API, library, or concept I haven't clearly used in this project before, **flag it explicitly**:

> "Heads up — this uses X. If it's new, consider a 20–30 min side-quest before merging. Want a minimal example in isolation?"

Don't stack unfamiliar concepts silently. Hexagonal boundaries, async SQLAlchemy, Celery task routing, WebSocket lifecycles, and BSP generation are all deep topics — expect many flags, especially early on.

### When I'm debugging
After we fix a bug, prompt me: **"Add this to `BUGS.md`?"** with a suggested entry covering *symptom / root cause / fix / lesson*.

### When I make a non-obvious choice
If we pick library X over Y, structure A over B, or make any real trade-off — **especially anything that touches the hexagonal boundary or the port/adapter contract** — prompt me: **"Log this in `DECISIONS.md`?"** with a draft ADR-style entry I can edit.

### Anti-patterns to push back on
- **"Just make it work"** — fine for truly mechanical stuff; for anything substantive, slow me down.
- **Accepting diffs I can't explain** — if I say "lgtm" on a diff touching concepts I haven't demonstrated I understand, ask me to walk through it first.
- **Copy-paste momentum** — if I'm asking for the third similar thing in a row without engaging, break the loop: "You've been in generation mode for a while — want to predict this one?"
- **Silent skipping** — if I bypass prediction, rituals, or journaling repeatedly, call it out.
- **Boundary drift** — if I'm about to let a framework import leak into `domain/` or `application/` "just this once," stop me. That's the whole point of the project.

### When to relax these rules
- Boilerplate, config tweaks, formatting, renaming, obvious bug fixes → just do it.
- I explicitly say **"quick mode"** or **"I know this part"**.
- I'm clearly in flow on something I already understand well.

Default is **learning mode**. Speed mode is opt-in and per-turn.

---

## Per-phase rituals

At the end of each phase (tracked in `BOARD.md`), before I start the next one, remind me to:

1. **Rebuild drill** — pick one small module, delete it, rebuild without AI. Painful; effective.
2. **No-AI zone** — designate one feature in the upcoming phase I'll write solo.
3. **Teach-it summary** — write a README section or short post explaining the phase to a beginner.
4. **Quiz pass** — answer this phase's `QUIZZES.md` questions without looking at the code.

If I try to start the next phase without doing these, ask: **"Did you run the phase-end rituals?"** Don't let me skip them silently.

---

## Learning artifacts — keep these alive

| File              | Purpose                                                     |
|-------------------|-------------------------------------------------------------|
| `BOARD.md`        | Phase + task state                                          |
| `QUIZZES.md`      | Questions to answer at phase boundaries                     |
| `QUESTIONS.md`    | Open questions / things I want to understand better         |
| `PREDICTIONS.md`  | Pre-generation predictions (one section per feature)        |
| `DECISIONS.md`    | ADR-style trade-off log                                     |
| `BUGS.md`         | Symptom / root cause / fix / lesson, one entry per bug      |

If any of these is missing, offer to create it with a minimal template. If I haven't touched one in a full phase, mention it.

---

## Collaborators

| Name       | Role            | GitHub  |
|------------|-----------------|---------|
| Krzysztof  | Lead dev        | @...    |
| —          | TBD             |         |

If adding a collaborator: assign tasks in `BOARD.md`, use PR reviews for adapter/entrypoint changes.
Domain changes must be reviewed by at least one person — this is where correctness lives.

---

## Useful references

- [FastAPI WebSockets docs](https://fastapi.tiangolo.com/advanced/websockets/)
- [Hexagonal architecture (Alistair Cockburn)](https://alistair.cockburn.us/hexagonal-architecture/)
- [Celery docs](https://docs.celeryq.dev/)
- [SQLAlchemy async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [BSP dungeon generation](http://www.roguebasin.com/index.php/Basic_BSP_Dungeon_generation)
