# HexCrawl — Task Board

Statuses: `🔲 backlog` · `🔄 in progress` · `✅ done` · `🚫 blocked`
Quiz: `⬜ not taken` · `🔁 retry` · `🏆 passed`
Assignees: `K` = Krzysztof · `?` = unassigned / open for collaborator

---

## Quiz system

- Every task has a quiz in `QUIZZES.md`. Take it **after** the task is done.
- **Task quiz**: 90% threshold (5-question quiz → need 5/5; 10-question → 9/10).
- **Phase quiz**: 90% threshold. Covers the whole phase. Do not start the next phase until passed.
- How to take a quiz: tell Claude → `"Quiz me on HexCrawl task 1.3"` or `"Quiz me on HexCrawl Phase 1"`.
- Claude asks questions one by one, grades each answer, then gives a full profile assessment: score, weak spots, what to revisit, strong areas.
- If you fail: study what Claude flags, then retry. No skipping forward.

---

## Phase 1 — Domain core
> Goal: pure Python, zero framework deps, fully tested.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 1.1 | Set up repo structure | ✅ | 🏆 | K | Match layout in CLAUDE.md |
| 1.2 | `Player` dataclass | ✅ | 🏆 | K | |
| 1.3 | `Enemy` dataclass + `BehaviourType` enum | ✅ | 🏆 | K | |
| 1.4 | `Item` dataclass + `ItemType` enum | ✅ | 🏆 | K | |
| 1.5 | `Floor` model | ✅ | 🏆 | K | tile grid, enemies, items, stairs pos |
| 1.6 | `Dungeon` model | ✅ | 🏆 | K | floors, current idx, seed (no player field — Option B) |
| 1.7 | `Score` dataclass + scoring formula | 🔲 | ⬜ | K | floors × kills × item multiplier |
| 1.8 | `TileType` enum | ✅ | 🏆 | K | wall, floor, stairs, door (shipped with 1.5) |
| 1.9 | `Action` type union | 🔲 | ⬜ | K | Move, Attack, UseItem, Descend, Abandon |
| 1.10 | `IGameRepository` Protocol | 🔲 | ⬜ | K | domain/ports/ |
| 1.11 | `IScoreRepository` Protocol | 🔲 | ⬜ | K | domain/ports/ |
| 1.12 | `ICachePort` Protocol | 🔲 | ⬜ | K | domain/ports/ |
| 1.13 | `DungeonGenerator` — BSP algorithm | 🔲 | ⬜ | K | Pure function, seeded random |
| 1.14 | Unit tests for `DungeonGenerator` | 🔲 | ⬜ | K | |
| 1.15 | `EnemyAI` — melee pathfinding | 🔲 | ⬜ | K | Manhattan distance |
| 1.16 | `GameService.process_turn()` | 🔲 | ⬜ | K | Core logic |
| 1.17 | Unit tests for `GameService` | 🔲 | ⬜ | K | Use fake repos |
| 1.18 | `ScoreService.compute()` | 🔲 | ⬜ | K | |
| 1.19 | Unit tests for `ScoreService` | 🔲 | ⬜ | K | |
| 📝 | **Phase 1 quiz** | — | ⬜ | K | Must pass before Phase 2 |

---

## Phase 2 — Persistence adapters
> Goal: wire up PostgreSQL and Redis without touching domain logic.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 2.1 | `docker-compose.yml` (postgres, redis) | 🔲 | ⬜ | K | |
| 2.2 | Alembic setup + initial migration | 🔲 | ⬜ | K | |
| 2.3 | SQLAlchemy ORM models | 🔲 | ⬜ | K | Separate from domain dataclasses |
| 2.4 | `PostgresGameRepository` | 🔲 | ⬜ | K | implements IGameRepository |
| 2.5 | `PostgresScoreRepository` | 🔲 | ⬜ | K | implements IScoreRepository |
| 2.6 | Integration tests for DB repos | 🔲 | ⬜ | K | testcontainers / pytest-docker |
| 2.7 | `RedisCache` implementing `ICachePort` | 🔲 | ⬜ | K | |
| 2.8 | Integration tests for `RedisCache` | 🔲 | ⬜ | K | |
| 2.9 | Supabase Auth setup | 🔲 | ⬜ | K | |
| 2.10 | JWT validation FastAPI dependency | 🔲 | ⬜ | K | `get_current_user` |
| 2.11 | Supabase Storage bucket setup | 🔲 | ⬜ | K | |
| 📝 | **Phase 2 quiz** | — | ⬜ | K | Must pass before Phase 3 |

---

## Phase 3 — Application use cases + API
> Goal: HTTP + WebSocket wired to domain through use cases.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 3.1 | `StartGame` use case | 🔲 | ⬜ | K | |
| 3.2 | `ProcessTurn` use case | 🔲 | ⬜ | K | Redis → service → Redis |
| 3.3 | `SubmitScore` use case | 🔲 | ⬜ | K | Triggers Celery task |
| 3.4 | FastAPI app setup | 🔲 | ⬜ | K | lifespan, CORS, routers |
| 3.5 | Auth endpoints | 🔲 | ⬜ | K | register + login |
| 3.6 | `POST /game/start` | 🔲 | ⬜ | K | |
| 3.7 | `GET /game/{id}` | 🔲 | ⬜ | K | |
| 3.8 | `POST /game/{id}/abandon` | 🔲 | ⬜ | K | |
| 3.9 | `WS /ws/game/{session_id}` | 🔲 | ⬜ | K | Full turn loop |
| 3.10 | `GET /leaderboard/global` | 🔲 | ⬜ | K | Served from Redis cache |
| 3.11 | `GET /leaderboard/weekly` | 🔲 | ⬜ | K | |
| 3.12 | `GET /leaderboard/me` | 🔲 | ⬜ | K | Requires auth |
| 3.13 | Pydantic v2 request/response schemas | 🔲 | ⬜ | K | |
| 3.14 | Integration tests — HTTP endpoints | 🔲 | ⬜ | K | |
| 3.15 | WebSocket test | 🔲 | ⬜ | K | pytest-asyncio |
| 📝 | **Phase 3 quiz** | — | ⬜ | K | Must pass before Phase 4 |

---

## Phase 4 — Celery workers
> Goal: async score recalc, map generation offload, scheduled weekly reset.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 4.1 | Celery app setup | 🔲 | ⬜ | K | broker + result = Redis |
| 4.2 | `score_recalc` task | 🔲 | ⬜ | K | Async leaderboard rebuild |
| 4.3 | `map_generation` task | 🔲 | ⬜ | K | Pre-gen floors 10+ |
| 4.4 | `weekly_leaderboard_reset` task | 🔲 | ⬜ | K | Archive + wipe |
| 4.5 | Celery Beat schedule | 🔲 | ⬜ | K | Mon 00:00 UTC |
| 4.6 | Add Celery + Beat to `docker-compose.yml` | 🔲 | ⬜ | K | |
| 4.7 | Test `SubmitScore` enqueues task correctly | 🔲 | ⬜ | K | |
| 📝 | **Phase 4 quiz** | — | ⬜ | K | Must pass before Phase 5 |

---

## Phase 5 — React frontend
> Goal: playable browser game. Keep it focused — backend is the star.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 5.1 | Vite + React setup | 🔲 | ⬜ | K | |
| 5.2 | Design 16×16 pixel tile set | 🔲 | ⬜ | K | GBA-style 4-colour palette |
| 5.3 | Canvas renderer | 🔲 | ⬜ | K | Draws Floor grid from game state JSON |
| 5.4 | Player sprite + movement animation | 🔲 | ⬜ | K | |
| 5.5 | Enemy sprites (3 types minimum) | 🔲 | ⬜ | K | |
| 5.6 | `useGameSocket` hook | 🔲 | ⬜ | K | Sends actions, receives state |
| 5.7 | Keyboard input handler | 🔲 | ⬜ | K | WASD / arrows / space |
| 5.8 | HUD (HP, floor, score, inventory) | 🔲 | ⬜ | K | |
| 5.9 | Game over screen | 🔲 | ⬜ | K | |
| 5.10 | Leaderboard page (global + weekly tabs) | 🔲 | ⬜ | K | |
| 5.11 | Auth screens (login / register) | 🔲 | ⬜ | K | |
| 5.12 | Supabase JWT auth flow | 🔲 | ⬜ | K | |
| 📝 | **Phase 5 quiz** | — | ⬜ | K | Must pass before Phase 6 |

---

## Phase 6 — Docker + AWS deploy
> Goal: working production deployment. Real infra, not just localhost.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 6.1 | `Dockerfile` for FastAPI (multi-stage) | 🔲 | ⬜ | K | |
| 6.2 | `Dockerfile` for Celery worker | 🔲 | ⬜ | K | Same image, different CMD |
| 6.3 | `docker-compose.prod.yml` | 🔲 | ⬜ | K | No hot reload, gunicorn |
| 6.4 | GitHub Actions CI — Python (ruff + black + mypy + pytest/cov) | ✅ | ⬜ | K | `.github/workflows/python.yml`, Postgres + Redis services, cov ≥ 80% |
| 6.4a | GitHub Actions CI — Frontend (eslint + prettier + tsc + vitest + build) | ✅ | ⬜ | K | `.github/workflows/frontend.yml`, guarded by `frontend/package.json` preflight |
| 6.4b | Dependabot config (pip + npm + actions + docker) | ✅ | ⬜ | K | `.github/dependabot.yml` |
| 6.5 | AWS VPC + subnets + security groups | 🔲 | ⬜ | K | |
| 6.6 | AWS RDS PostgreSQL | 🔲 | ⬜ | K | |
| 6.7 | AWS ElastiCache Redis | 🔲 | ⬜ | K | |
| 6.8 | AWS ECS Fargate task definition | 🔲 | ⬜ | K | |
| 6.9 | AWS ALB | 🔲 | ⬜ | K | |
| 6.10 | GitHub Actions CD (deploy on merge to main) | 🔲 | ⬜ | K | |
| 6.11 | Domain + HTTPS (Route53 + ACM) | 🔲 | ⬜ | K | |
| 📝 | **Phase 6 quiz** | — | ⬜ | K | Final sign-off |

---

## Backlog / Ideas

### Gameplay
- Boss enemies every 5th floor
- Item shop between floors
- Persistent character unlocks
- Replay system (store action log, replay from seed)
- Discord webhook on new #1 global score
- Mobile touch controls
- **Speed / Luck stats on `Player`** (turn-order resolution + crit / loot RNG) — deferred from v1, which ships with HP / Attack / Defense only

### CI / Quality pipelines (suggested — not yet scheduled)
- **`import-linter` in CI** — fail the build if anything inside `src/domain/` or `src/application/` imports a forbidden framework (fastapi/sqlalchemy/redis/celery/pydantic). This automates the golden hexagonal rule that `/audit` checks manually.
- **CodeQL** (`github/codeql-action`) — weekly + on PR; covers Python and JS/TS security patterns for free on public repos.
- **Semgrep** — more targeted rulesets (e.g. flask/fastapi auth checks) than CodeQL.
- **Trivy image scan** — once the FastAPI and Celery Dockerfiles exist (Phase 6 tasks 6.1 / 6.2), scan built images for CVEs on every push to `main`.
- **Alembic head-check** — `alembic heads | wc -l == 1` as a CI step once migrations exist, to prevent conflicting heads from slipping into `main`.
- **WebSocket smoke test** — spin up the full compose stack in CI and hit `/ws/game/{session_id}` with a canned turn sequence; catches wiring regressions unit tests miss.
- **Load test on leaderboard endpoints** — `k6` or `locust` scheduled weekly against a staging deploy; the endpoint has a latency budget per `QUIZZES.md` Phase 3 summary quiz.
- **Coverage trend publishing** — upload `coverage.xml` to Codecov / Coveralls so PRs show coverage diff, not just pass/fail on the 80% threshold.
- **Release / tag workflow** — on version tag, build + push Docker images to ECR (once Phase 6 task 6.10 lands).
- **Preview deploys for PRs** — spin up a per-PR environment; optional, costs money on AWS, cheap on Fly.io or Render.
- **Mutation testing** (`mutmut` for Python, `stryker` for TS) — optional but a strong signal for the domain layer where correctness matters most; would run on a schedule, not every PR.

---

## Done

_(move tasks here as they complete)_

---

*Last updated: 2026-04 — Krzysztof*
