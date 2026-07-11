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
Total: **78 tasks across 6 phases, ~84 sessions, ~17 weeks (~4 months) end-to-end.**

Anchored forward from **2026-06-08**. As of **2026-06-24**: **48/78 tasks done** (Phases 1–3 complete; three CI tasks done early in Phase 6). Remaining: **30 tasks**, ~**8 weeks (~2 months)** → target completion **late August–early September 2026**. Phases 1–3 all closed ahead of estimate — the M3 backend-MVP milestone landed ~2–3 weeks early. (Note: the prior count of "43/77, Phase 3 at 10/15" undercounted Phase 3 by one — the table had 11 done at 3.11; corrected here.)

> ⚠️ Task counts and "done" figures are real (counted from the tables below). The **Sessions / Weeks / Target** columns are estimates, not commitments — adjust as real velocity lands.
>
> 📋 **2026-07-11:** Phase 7 (audit remediation, 20 tasks) added from the `/audit` run — **not** counted in the original 78/6-phase totals above. It is an independent phase: its tasks have no ordering dependency on Phases 4–6 and can be interleaved at will. The three 🔴 tasks (7.1–7.3) gate the M3 claim "scores persist" actually holding end-to-end.

---

## Milestones

Weeks/dates below are **remaining work projected from 2026-06-08** at 10 h/week.

| Milestone | Phase | Tasks (done/total) | Sessions (rem.) | Weeks (rem.) | Target date |
|-----------|-------|--------------------|-----------------|--------------|-------------|
| M1 — Domain core | Phase 1 | 19/19 ✅ | — | — | **done** |
| M2 — Data persists | Phase 2 | 11/11 ✅ | — | — | **done** |
| M3 — Playable via API + WS | Phase 3 | 15/15 ✅ | — | — | **done** |
| **M3 = backend MVP** | | | | | **Turn loop over HTTP/WS, scores persist** |
| M4 — Async workers live | Phase 4 | 0/7 | ~9 | ~2 | mid-to-late July 2026 |
| M5 — Browser game playable | Phase 5 | 0/13 | ~14 | ~3 | mid-August 2026 |
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
| 3.12 | `GET /leaderboard/me` | ✅ | ⬜ | K | Authed per-user board; `GetMyScores` (uncached → reads PG via `top_n_for_user` + `rank_of`); `MyScoresResponse` (global/weekly rank + paginated entries); 401 unauth |
| 3.13 | Pydantic v2 request/response schemas | ✅ | ⬜ | K | Schemas shipped incrementally (3.6/3.10); 3.13 = RFC 7807 Problem Details retrofit — `application/problem+json` via app-wide `HTTPException`/`RequestValidationError` handlers, `WWW-Authenticate` preserved |
| 3.14 | Integration tests — HTTP endpoints | ✅ | ⬜ | K | All HTTP endpoints covered via `TestClient` + fakes: start/get/abandon/global/weekly/me/problem-details |
| 3.15 | WebSocket test | ✅ | ⬜ | K | Turn loop covered by `test_game_ws.py` (auth handshake / authz / resilience / game-over / 1008·1000·1011 closes) |
| 📝 | **Phase 3 quiz** | — | ⬜ | K | Must pass before Phase 4 |

---

## Phase 4 — Celery workers
> Goal: async score recalc, map generation offload, scheduled weekly reset.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 4.1 | Celery app setup | ✅ | ⬜ | K | broker + result = Redis; JSON-only serialisation (no pickle), UTC clock; `task_failure` → structlog log-and-drop (QUESTIONS.md 4.1, no DLQ); instance `app` in `adapters/tasks/celery_app.py` |
| 4.2 | `score_recalc` task | ✅ | ⬜ | K | Async leaderboard rebuild |
| 4.3 | `map_generation` task | ✅ | ⬜ | K | Pre-gen floors 10+ |
| 4.4 | `weekly_leaderboard_reset` task | ✅ | ⬜ | K | Archive (new `weekly_leaderboard_archive` table via `IScoreAdminRepository`) + non-destructive view-reset (refresh `leaderboard:WEEKLY` cache); Beat-triggered, no queue port; schedule is 4.5 |
| 4.5 | Celery Beat schedule | ✅ | ⬜ | K | Mon 00:00 UTC |
| 4.6 | Add Celery + Beat to `docker-compose.yml` | ✅ | ⬜ | K | Shared root `Dockerfile`; worker + singleton `beat` services |
| 4.7 | Test `SubmitScore` enqueues task correctly | ✅ | ⬜ | K | |
| 📝 | **Phase 4 quiz** | — | ⬜ | K | Must pass before Phase 5 |

---

## Phase 5 — React frontend
> Goal: playable browser game. Keep it focused — backend is the star.

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 5.1 | Vite + React setup | ✅ | ⬜ | K | Zustand + Tailwind v4 + React Router; `/api`+`/ws` dev proxy |
| 5.2 | Design 16×16 pixel tile set | ✅ | ⬜ | K | 🎨 **floor-layout tiles** — wall/floor/stairs/door; GBA-style 4-colour palette; hand-authored via `assets/tools/gen_tiles.py`, seamless, palette-pure |
| 5.3 | Canvas renderer | ✅ | ⬜ | K | 🎨 consumes the 5.2 tile set; draws Floor grid from game state JSON |
| 5.4 | Player sprite + movement animation | ✅ | ⬜ | K | 🎨 **player sprite** (+ idle/move frames) |
| 5.5 | Enemy sprites (3 types minimum) | ✅ | ⬜ | K | 🎨 **enemy sprites** — melee / ranged / boss |
| 5.5a | Item sprites (per `ItemType`) | ✅ | ⬜ | K | 🎨 **item sprites** — potion / weapon / etc.; render on floor grid + HUD inventory (`ItemType` enum, 1.4) |
| 5.6 | `useGameSocket` hook | ✅ | ⬜ | K | Sends actions, receives state |
| 5.7 | Keyboard input handler | ✅ | ⬜ | K | WASD / arrows / space |
| 5.8 | HUD (HP, floor, score, inventory) | ✅ | ⬜ | K | HTML-over-canvas (`src/hud/`); kills client-counted from `enemy_killed` events (no live score on the wire — shown as floor/kills/turns); inventory rack structural until backend inventory ships; + largest-fit canvas scaling (5.3 deferral) |
| 5.9 | Game over screen | ✅ | ⬜ | K | 🎨 DOM overlay over the canvas (`src/gameover/`); run lifecycle as an explicit store state machine (`phase`: idle→playing→game_over, cause from `player_died`/`run_abandoned` events); shows score inputs only (no score on the wire; abandoned runs score nothing); New Run = store reset until start-game ships (5.11/5.12) |
| 5.10 | Leaderboard page (global + weekly tabs) | ✅ | ⬜ | K | 🎨 `src/leaderboard/` feature folder (model split); raw-fetch hook with explicit loading/error/empty/success states + abort-on-cleanup; tabs remount the board per period; added the missing `/api`→`/v1` proxy rewrite (first HTTP consumer) |
| 5.11 | Auth screens (login / register) | 🔲 | ⬜ | K | 🎨 **screen layout** |
| 5.12 | Supabase JWT auth flow | 🔲 | ⬜ | K | |
| 📝 | **Phase 5 quiz** | — | ⬜ | K | Must pass before Phase 6 |

> 🎨 **Design assets needed.** Rows marked 🎨 need pixel art / UI mockups produced (or sourced)
> before the task can be built. All visual design work lives in Phase 5 — Phases 1–4 are pure
> backend logic with no art dependency (the BSP "floor layout" of task 1.13 is *algorithmic*, not visual).
>
> 📋 **Generation shot-list + prompts:** [`docs/art-assets.md`](docs/art-assets.md) — the 13 base
> assets (player/enemies/items/tiles) with ready-to-paste ComfyUI prompts and the shared GBA palette
> ([`docs/palettes/gameboy-4.gpl`](docs/palettes/gameboy-4.gpl)).
>
> 🟢 **Draft sprites generated:** [`assets/`](assets/) holds AI-generated draft sprites named by
> domain enum + [`assets/manifest.json`](assets/manifest.json) for the renderer. 12/13 done; only
> **`tiles/stairs.png` remains** (hand-draw — SD1.5 can't make a staircase tile). A few are `rough`
> (skeleton, armor, door) — see the manifest `status` field.
>
> | Asset | Task | Notes |
> |-------|------|-------|
> | **Floor-layout tiles** — wall, floor, stairs, door | 5.2 → 5.3 | 16×16, GBA 4-colour palette; the visual vocabulary the canvas renders |
> | **Player sprite** (+ idle / move frames) | 5.4 | |
> | **Enemy sprites** — melee, ranged, boss | 5.5 | 3 types min; boss variant ties to "boss every 5th floor" (backlog) |
> | **Item sprites** — potion / weapon / etc. | 5.5a | Render on the floor grid and in the HUD inventory; one per `ItemType` (enum, task 1.4) |
> | **HUD layout** — HP / floor / score / inventory | 5.8 | |
> | **Game over screen** | 5.9 | |
> | **Leaderboard page** — global + weekly tabs | 5.10 | |
> | **Auth screens** — login / register | 5.11 | |

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

## Phase 7 — Audit remediation (2026-07-11)
> Source: `/audit` run 2026-07-11 (3 critical, 12 warnings, 30 info). **Independent phase** — every
> task is self-contained and can be picked up regardless of Phase 4–6 progress or ordering. No
> phase-gate quiz requirement between this and other phases. Severity tags: 🔴 critical, 🟠 warning, 🔵 info.

### Critical — unwired pipelines (the documented core loop cannot run end-to-end)

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 7.1 | 🔴 Wire `SubmitScore` on game-over | 🔲 | ⬜ | K | WS handler (`entrypoints/ws/router_game.py:184`) closes without scoring; `SubmitScore` has zero production callers. Aggregate `kills` **server-side** from `EnemyKilled` events across the run (add a counter to `Dungeon` or per-run event log — never trust a client-sent count), derive `abandoned` from `RunAbandoned`, call inside the per-turn UoW in `GameSessionRunner` with `PostgresScoreRepository` + `CeleryScoreRecalcQueue` |
| 7.2 | 🔴 Enemy + item spawn service | 🔲 | ⬜ | K | Generator emits `enemies=[]`, `items={}` (`dungeon_generator.py:145`) and nothing downstream populates them — combat/death/non-zero scores unreachable; `enemy_ai`/`fov`/sprites are test-only. Seeded from `(seed, floor_index)` for determinism; exclude the player spawn tile |
| 7.3 | 🔴 Floor progression + deep-floor pre-gen wiring | 🔲 | ⬜ | K | `Descend` always rejects `no_next_floor` (`start_game.py:111` builds `floors=[floor0]`; nothing appends). Generate next floor on descend: shallow inline, floors ≥ new `DEEP_FLOOR_THRESHOLD = 10` via `IMapGenerationQueue` (currently zero consumers) with cache-miss inline fallback splicing `deserialize_floor` into `dungeon.floors` |

### Warnings — state integrity, resilience, hygiene

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 7.4 | 🟠 Terminal run status + guard | 🔲 | ⬜ | K | No `ACTIVE/DEAD/ABANDONED` status anywhere; dead/abandoned runs are resumable and abandon is replayable. Add status to model + persistence; reject in `ProcessTurn` and at WS connect (`GameAlreadyOverError` → 1008/409); unit + reconnect-after-death WS tests. Do before/with 7.1 |
| 7.5 | 🟠 Per-game concurrency guard | 🔲 | ⬜ | K | GET→mutate→SET race in `process_turn.py:87` / `abandon_game.py:85`: two sockets on one game (or abandon vs turn) silently lose writes. Redis `SET NX` lock or blob version counter — or enforce one active socket per game id |
| 7.6 | 🟠 Publish cache after PG commit | 🔲 | ⬜ | K | `cache.set` runs before `session.begin()` exits (`dependencies.py:200-226`), so a failed commit leaves Redis ahead of PG for 2h (phantom runs from `StartGame` too). Move cache publish after the transaction block; fix the misleading "durable save goes first" comments in `process_turn.py:92` |
| 7.7 | 🟠 Corrupt cache blob → PG fallback | 🔲 | ⬜ | K | `deserialize_game_state` raises uncaught in all 3 loaders (`process_turn.py:110`, `get_game.py:90`, `abandon_game.py:109`) → run bricked until TTL. Catch `(KeyError, ValueError, TypeError)`, log, fall through to checkpoint — mirror `get_leaderboard.py:62` |
| 7.8 | 🟠 Weekly archive gap recovery | 🔲 | ⬜ | K | `archive_completed_week` only archives `current_week_start − 7d` (`score_admin_repository.py:56`); Beat down over a Monday = week lost forever, contradicting the module's own "caught by the following Monday" claim. Walk forward from `MAX(week_start) + 7d`, or log loudly on gap |
| 7.9 | 🟠 Handle binary WS frames | 🔲 | ⬜ | K | Binary frame → `KeyError` from Starlette `receive_json`, uncaught at `ws/router_game.py:111`/`:147` → traceback + dead connection, pre-auth. Catch `KeyError` or use `receive_text()` + `json.loads` |
| 7.10 | 🟠 `BehaviourType` dispatch `match` | 🔲 | ⬜ | K | `decide_action` never reads `enemy.behaviour` (`enemy_ai.py:68-103`) — the documented "seam" is prose-only; a 4th type silently gets melee. Add exhaustive `match enemy.behaviour:` (arms may share melee logic) so mypy enforces it, like `game_service.py:138` |
| 7.11 | 🟠 Delete dead config | 🔲 | ⬜ | K | `jwt_secret` is *required* but read nowhere (auth is JWKS-asymmetric); also unused: `supabase_anon_key`, `supabase_service_role_key`, both storage buckets (`config.py:12-20`). Remove from Settings, `.env.example`, `docker-compose.yml:14`, CLAUDE.md env table |
| 7.12 | 🟠 Real e2e WS test (or fix docs) | 🔲 | ⬜ | K | `tests/e2e/ws/` holds only `__init__.py` vs CLAUDE.md's testing tree; `test_game_ws.py` is in-process + `FakeRunner`. Either one real test (uvicorn + real socket + testcontainers, real `GameSessionRunner`) or delete `tests/e2e/` and amend CLAUDE.md |
| 7.13 | 🟠 Test the real UoW boundary | 🔲 | ⬜ | K | `dependencies.py` at 56%: `get_session` + `GameSessionRunner.load_authorized/process` (the only place commits happen, ADR-0006) executed by no test; `FakeRunner` can drift. Integration test over testcontainers or unit test with fake sessionmaker (pattern: `test_weekly_leaderboard_reset.py:110`) |
| 7.14 | 🟠 Create `BUGS.md` | 🔲 | ⬜ | K | Listed in CLAUDE.md learning artifacts, never created. Seed with symptom/root-cause/fix/lesson entries from 7.6 and 7.8 |

### Info — batched cleanups (each row = one small PR)

| # | Task | Status | Quiz | Who | Notes |
|---|------|--------|------|-----|-------|
| 7.15 | 🔵 Docs reconciliation pass | 🔲 | ⬜ | K | CLAUDE.md: score formula stale (code = `floors² × kills × mult − penalty`, per BOARD 1.7); "explicit save" trigger doesn't exist (implement or strike); API table missing `/v1` prefix note; Celery row `weekly_leaderboard` → `weekly_leaderboard_reset`; diagram/repo-layout drift (undiagrammed app modules, `fov.py`/`spawn.py`, `adapters→application` task arrow, tests-tree); add `CORS_ORIGINS` to `.env.example` + env table |
| 7.16 | 🔵 Security hardening batch | 🔲 | ⬜ | K | Set `--ws-max-size` (few KiB) in launch/Dockerfile; post-auth WS idle timeout; `allow_credentials=False` + narrow `allow_headers` (`main.py:112`); per-user active-run cap on `POST /game/start`. (403/404 existence leak + JWKS→401 are documented-accepted — no action) |
| 7.17 | 🔵 Gameplay/WS niggles | 🔲 | ⬜ | K | Skip enemy-AI round on `FloorDescended` turn (free hit on new floor, `game_service.py:156,274`); `spawn_position` excludes enemy tiles (`spawn.py:26`); WS connect-path infra faults → deliberate 1011 (`ws/router_game.py:83,91`); `asyncio.to_thread` BSP in `StartGame` when 7.3 multiplies generation |
| 7.18 | 🔵 Test refinements | 🔲 | ⬜ | K | Inject "now" into weekly-window integration tests (Monday-boundary flake); unit mapper test for `score_admin_repository`; cover `game_service.py` defensive branches (:312-316, :343-345, :422 via `ai_decide` seam); Protocol-conformance tests for the 3 untested ports; fake timers for `GameCanvas.test.tsx` flush |
| 7.19 | 🔵 Dead-weight cleanup | 🔲 | ⬜ | K | Drop wire parsing for `PickUp`/`UseItem`/`Open` until they ship (or keep with comment); underscore `compute_fov` (only `has_los` consumes it); trim `domain/services/__init__.py` `__all__` (5 unconsumed exports); make `TILE_URLS`/`ENEMY_URLS` module-private; replace empty `/v1/auth` router include with a comment in `main.py` |
| 7.20 | 🔵 Constants & schema | 🔲 | ⬜ | K | Derive `PREGEN_FLOOR_TTL_SECONDS` from `GAME_STATE_TTL_SECONDS` (or document independence); single-source the `±2**63` seed bounds (`schemas.py` ← `start_game.py`); composite index `(user_id, value DESC, computed_at ASC)` for `/leaderboard/me` when a load target exists |
| 📝 | **Phase 7 quiz** | — | ⬜ | K | Quizzes currently disabled — owed on re-enable |

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

*Last updated: 2026-07-11 — Phase 7 (audit remediation) added from `/audit` findings*
