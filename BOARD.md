# HexCrawl — Task Board

Statuses: `🔲 backlog` · `🔄 in progress` · `✅ done` · `🚫 blocked`
Quiz: `⬜ not taken` · `🔁 retry` · `🏆 passed`
Assignees: `K` = Krzysztof · `?` = unassigned / open for collaborator

---

## Quiz system

> 🚫 **QUIZZES DISABLED** (set 2026-06-12, by Krzysztof). While disabled, do **not**
> offer/require quizzes, do **not** run quiz rituals, and do **not** gate task pickup or
> phase progression on quiz state. **Preserve all quiz cells as-is** (`⬜`/`🔁`/`🏆`) —
> they are the backlog owed when quizzes are re-enabled. Re-enable only when Krzysztof
> says so (e.g. "enable quizzes"), then remove this banner. Owed on re-enable: task 2.4
> (`⬜`) and every phase summary quiz.

- Every task has a quiz in `QUIZZES.md`. Take it **after** the task is done.
- **Task quiz**: 90% threshold (5-question quiz → need 5/5; 10-question → 9/10).
- **Phase quiz**: 90% threshold. Covers the whole phase. Do not start the next phase until passed.
- How to take a quiz: tell Claude → `"Quiz me on HexCrawl task 1.3"` or `"Quiz me on HexCrawl Phase 1"`.
- Claude asks questions one by one, grades each answer, then gives a full profile assessment: score, weak spots, what to revisit, strong areas.
- If you fail: study what Claude flags, then retry. No skipping forward.

---

## Pace

**2 hours/day, 5 days/week = 10 hours/week.** (~1 session ≈ 2 hours.)
Vibe coding with AI assistance. Estimates include quiz time and ~20% debugging buffer.
Total: **77 tasks across 6 phases, ~84 sessions, ~17 weeks (~4 months) end-to-end.**

Anchored forward from **2026-06-08**. As of **2026-06-24**: **43/77 tasks done** (Phases 1 & 2 complete; Phase 3 at 10/15; three CI tasks done early in Phase 6). Remaining: **34 tasks**, ~**9–10 weeks (~2 months)** → target completion **late August–early September 2026**. Phases 1 & 2 closed ahead of estimate, and Phase 3 is tracking ahead too.

> ⚠️ Task counts and "done" figures are real (counted from the tables below). The **Sessions / Weeks / Target** columns are estimates, not commitments — adjust as real velocity lands.

---

## Milestones

Weeks/dates below are **remaining work projected from 2026-06-08** at 10 h/week.

| Milestone | Phase | Tasks (done/total) | Sessions (rem.) | Weeks (rem.) | Target date |
|-----------|-------|--------------------|-----------------|--------------|-------------|
| M1 — Domain core | Phase 1 | 19/19 ✅ | — | — | **done** |
| M2 — Data persists | Phase 2 | 11/11 ✅ | — | — | **done** |
| M3 — Playable via API + WS | Phase 3 | 10/15 | ~6 | ~1.5 | early-to-mid July 2026 |
| **M3 = backend MVP** | | | | | **Turn loop over HTTP/WS, scores persist** |
| M4 — Async workers live | Phase 4 | 0/7 | ~9 | ~2 | mid-to-late July 2026 |
| M5 — Browser game playable | Phase 5 | 0/12 | ~14 | ~3 | mid-August 2026 |
| **M5 = playable game** | | | | | **End-to-end in the browser (local)** |
| M6 — Deployed to AWS | Phase 6 | 3/13 | ~14 | ~3 | late August–early September 2026 |
| **M6 = v1 release** | | | | | **Live on AWS ECS Fargate, HTTPS** |

**Key milestones:**
- **M3 (early-to-mid July)** — backend MVP. Full turn loop over HTTP + WebSocket, scores persisted, leaderboard served. No frontend yet.
- **M5 (mid-August)** — playable game. React canvas client wired to the WS turn loop; end-to-end in the browser against local infra.
- **M6 (late Aug–early Sept)** — v1 release. Dockerised, deployed to AWS ECS Fargate behind an ALB with HTTPS.

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
| 1.7 | `Score` dataclass + scoring formula | ✅ | 🏆 | K | floors_reached² × kills × item multiplier, minus damage penalty |
| 1.8 | `TileType` enum | ✅ | 🏆 | K | wall, floor, stairs, door (shipped with 1.5) |
| 1.9 | `Action` type union | ✅ | 🏆 | K | Move, Attack, UseItem, Descend, Abandon, Wait, PickUp, Open — frozen dataclasses + Direction enum |
| 1.10 | `IGameRepository` Protocol | ✅ | 🏆 | K | domain/ports/ |
| 1.11 | `IScoreRepository` Protocol | ✅ | 🏆 | K | domain/ports/ |
| 1.12 | `ICachePort` Protocol | ✅ | 🏆 | K | domain/ports/ |
| 1.13 | `DungeonGenerator` — BSP algorithm | ✅ | 🏆 | K | Pure function, seeded random |
| 1.14 | Unit tests for `DungeonGenerator` | ✅ | 🏆 | K | |
| 1.15 | `EnemyAI` — melee pathfinding | ✅ | 🏆 | K | Manhattan distance |
| 1.16 | `GameService.process_turn()` | ✅ | 🏆 | K | Core logic |
| 1.17 | Unit tests for `GameService` | ✅ | 🏆 | K | No fake needed — `process_turn` takes no ports (see QUESTIONS.md 1.16) |
| 1.18 | `ScoreService.compute()` | ✅ | 🏆 | K | |
| 1.19 | Unit tests for `ScoreService` | ✅ | 🏆 | K | |
| 📝 | **Phase 1 quiz** | — | 🏆 | K | Must pass before Phase 2 |

---

## Phase 2 — Persistence adapters
> Goal: wire up PostgreSQL and Redis without touching domain logic.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 2.1 | `docker-compose.yml` (postgres, redis) | ✅ | 🏆 | K | postgres + redis, named pgdata volume, healthchecks |
| 2.2 | Alembic setup + initial migration | ✅ | 🏆 | K | async env.py, Settings-sourced URL, naming convention on Base, empty baseline |
| 2.3 | SQLAlchemy ORM models | ✅ | 🏆 | K | Separate from domain dataclasses |
| 2.4 | `PostgresGameRepository` | ✅ | ⬜ | K | implements IGameRepository |
| 2.5 | `PostgresScoreRepository` | ✅ | ⬜ | K | implements IScoreRepository |
| 2.6 | Integration tests for DB repos | ✅ | ⬜ | K | testcontainers / pytest-docker |
| 2.7 | `RedisCache` implementing `ICachePort` | ✅ | ⬜ | K | |
| 2.8 | Integration tests for `RedisCache` | ✅ | ⬜ | K | |
| 2.9 | Supabase Auth setup | ✅ | ⬜ | K | |
| 2.10 | JWT validation FastAPI dependency | ✅ | ⬜ | K | `get_current_user` |
| 2.11 | Supabase Storage bucket setup | ✅ | ⬜ | K | private `saves` (pre-signed URLs) + public-read `avatars`; runbook in docs/storage-setup.md |
| 📝 | **Phase 2 quiz** | — | ⬜ | K | Must pass before Phase 3 |

---

## Phase 3 — Application use cases + API
> Goal: HTTP + WebSocket wired to domain through use cases.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 3.1 | `StartGame` use case | ✅ | ⬜ | K | seed→floor0→persist→cache; serializer in `application/game_state.py` |
| 3.2 | `ProcessTurn` use case | ✅ | ⬜ | K | Redis → service → Redis |
| 3.3 | `SubmitScore` use case | ✅ | ⬜ | K | sync-persist Score → enqueue score_recalc via IScoreRecalcQueue; deterministic score_id (idempotent); abandoned → no score |
| 3.4 | FastAPI app setup | ✅ | ⬜ | K | lifespan, CORS, routers |
| 3.5 | Auth endpoints | ✅ | ⬜ | K | Frontend-only auth (Supabase SDK); backend verify-only, no routes — ADR-0007 |
| 3.6 | `POST /game/start` | ✅ | ⬜ | K | 201 + Location + full game state; auth via get_current_user; GameStateResponse shared with 3.7 |
| 3.7 | `GET /game/{id}` | ✅ | ⬜ | K | cache-first/PG-fallback read (no write-back); authZ in use case → 403 foreign / 404 missing; reuses GameStateResponse |
| 3.8 | `POST /game/{id}/abandon` | ✅ | ⬜ | K | AbandonGame use case: load→authZ→domain Abandon→PG checkpoint→cache refresh; no score; 200 + final state, 403 foreign / 404 missing (mirrors 3.7) |
| 3.9 | `WS /ws/game/{session_id}` | ✅ | ⬜ | K | Full turn loop: first-message auth → GetGame authZ → per-turn UoW over ProcessTurn → state+events frames; resilient loop, 1008/1000/1011 closes |
| 3.10 | `GET /leaderboard/global` | ✅ | ⬜ | K | Served from Redis cache |
| 3.11 | `GET /leaderboard/weekly` | ✅ | ⬜ | K | Mirror of 3.10 with `LeaderboardPeriod.WEEKLY`; weekly window in `top_n`, distinct cache key `leaderboard:WEEKLY`; public, no auth |
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

*Last updated: 2026-06-24 — Krzysztof*
