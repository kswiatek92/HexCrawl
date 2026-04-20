# HexCrawl — Open Questions

Parked decisions the developer needs to answer before (or during) implementation.
`- [ ]` = open · `- [x]` = answered (write the decision inline).

Rules:
- Cross a question off only after the decision is recorded — inline here, or promoted to `CLAUDE.md` if it's durable.
- `/pickup` surfaces any unchecked item before letting you grab a new task.
- Each question is scoped to the task(s) or phase it blocks.

---

## Phase 1 — Domain core

### Player (task 1.2)
- [x] Starting HP? → **20**.
- [x] Which base stats and starting values? → **HP, Attack (start 3), Defense (start 1)**. Speed/Luck deferred to v2 (see Backlog in BOARD.md).
- [x] Inventory capacity — fixed slot count, weight-based, or unbounded? → **No general inventory / bag.** Items live in dedicated equipment slots only (see next answer).
- [x] Equipment slots (weapon / armor / accessory) or one generic bag? → **Dedicated slots only**: `weapon`, `armor`, `shield`, and a `consumables` stack (potions, cap 5 for v1). Picking up when a slot is full replaces the current item; the old item drops on the tile.
- [x] Level / XP system in v1, or flat stats with gear-only growth? → **No XP.** Flat stats, gear-only growth.

### Enemy + BehaviourType (task 1.3)
- [ ] HP / damage scaling across floors — linear, exponential, hand-authored tables? **Constraint:** floor-1 melee damage must cap at 1 HP per hit (Player starts at 20 HP, so a stand-still death takes ~20 turns — leaves room to counter-attack / heal).
- [ ] Ranged enemies: which tile types block line-of-sight? (walls only? doors?)
- [ ] Boss cadence — every 5th floor (per Backlog in BOARD.md) or something else for v1?
- [ ] Does `BehaviourType` start as `MELEE | RANGED | BOSS` exactly, or more granular (e.g. `MELEE_AGGRESSIVE`, `MELEE_COWARD`)?

### Item + ItemType (task 1.4)
- [ ] Which item types ship in v1? (potions, weapons, armor, scrolls, gold, keys?)
- [ ] Stackable items — flat count on one instance, or many instances?
- [ ] Item multiplier for scoring — per-type weight, per-rarity, or per-item value?

### Floor (task 1.5)
- [ ] Grid dimensions — fixed (e.g. 80×50) or scales with floor index?
- [ ] One down-staircase per floor, or multiple branches?
- [ ] Do items and enemies live on the `Floor` or in separate collections keyed by position?

### Dungeon (task 1.6)
- [ ] Total depth — fixed (e.g. 20 floors) or endless?
- [ ] Seed source — client-provided, server-random, or both (daily seed mode)?
- [ ] Is the player ref stored on `Dungeon` or passed separately to services?

### Score (task 1.7)
- [ ] Exact formula — literally `floors × kills × item_multiplier`, or weighted (e.g. `floors² × kills × item_multiplier`)?
- [ ] Penalties for damage taken, turns used, or deaths?
- [ ] Minimum floor for a score to count at all?

### TileType (task 1.8)
- [ ] Tiles beyond `WALL | FLOOR | STAIRS | DOOR`? (trap, water, chest, altar?)

### Action (task 1.9)
- [ ] Actions beyond Move/Attack/UseItem/Descend/Abandon? Likely candidates: `Wait`, `PickUp`, `DropItem`, `Open` (door), `Equip`.
- [ ] Is `Attack` implicit on `Move into enemy tile`, or a separate explicit action?

### DungeonGenerator (task 1.13)
- [ ] BSP parameters — min room size, max recursion depth, corridor style (L-shape / straight)?
- [ ] Post-gen reachability check — enforce or trust the algorithm?
- [ ] Enemy / item placement — part of this generator or a separate step?

### EnemyAI (task 1.15)
- [ ] Line-of-sight gating, or blind Manhattan pathing?
- [ ] FOV algorithm if LOS is needed — shadowcasting, raycasting, symmetric-shadowcasting?
- [ ] Wake-up radius — enemies chase always, or only when within N tiles?

---

## Phase 2 — Persistence adapters

- [ ] Integration test runner — `testcontainers-python` or `pytest-docker`? (task 2.6, 2.8)
- [ ] Supabase — cloud project from day one, or local `supabase-cli` stack for dev? (task 2.9)
- [ ] Active game state schema — one row per session with a JSONB blob, or fully relational? (task 2.3)
- [ ] JWT refresh-token flow — Supabase SDK on frontend only, or does the backend rotate too? (task 2.10)
- [ ] Alembic naming convention for constraints/indexes — set in `env.py` now? (task 2.2)

---

## Phase 3 — Application use cases + API

- [ ] Rate limiting — none, in-process (slowapi), or Redis-backed? (task 3.4)
- [ ] CORS allowed origins — `localhost:5173` for dev; prod domain TBD. (task 3.4)
- [ ] Leaderboard pagination — cursor or offset/limit? Page size? (tasks 3.10–3.12)
- [ ] WebSocket auth — JWT in query string, `Sec-WebSocket-Protocol`, or first client message? (task 3.9)
- [ ] Error response shape — FastAPI default, or RFC 7807 Problem Details? (task 3.13)
- [ ] API versioning — `/v1/` prefix from the start, or add later? (task 3.4)
- [ ] `SubmitScore` — sync-persist then enqueue recalc, or enqueue both? (task 3.3)

---

## Phase 4 — Celery workers

- [ ] Task retry policy — default exponential backoff, or custom per-task? (tasks 4.2–4.4)
- [ ] Dead-letter / failed-task handling — Sentry, dedicated queue, or log-and-drop? (task 4.1)
- [ ] `map_generation` output — fully rendered `Floor` pushed to Redis, or just the seed? (task 4.3)
- [ ] Weekly reset archive — snapshot to DB table, to S3/Supabase Storage, or both? (task 4.4)

---

## Phase 5 — React frontend

- [ ] State management — Zustand, Redux Toolkit, or plain context + hooks? (task 5.1)
- [ ] Styling — Tailwind, CSS Modules, or vanilla CSS? (task 5.1)
- [ ] Router — React Router, TanStack Router, or no router (single-page)? (task 5.1)
- [ ] Canvas target resolution — 240×160 (GBA-native) scaled up, or device-native? (task 5.3)
- [ ] Exact 4-colour palette hex values — pick now or iterate? (task 5.2)
- [ ] Sprite source — hand-author, generate, or use an open tileset? (tasks 5.2, 5.4, 5.5)
- [ ] Testing scope — Vitest + RTL only, or add Playwright for e2e? (implied by CI)

---

## Phase 6 — Docker + AWS deploy

- [ ] AWS region — `eu-west-1`, `us-east-1`, elsewhere? (task 6.5)
- [ ] Secrets — AWS Secrets Manager, SSM Parameter Store, or env-only? (task 6.8)
- [ ] Log aggregation — CloudWatch Logs only, or ship to Loki / Datadog? (task 6.8)
- [ ] Metrics / alerting — CloudWatch alarms, Prometheus/Grafana, or nothing for v1? (task 6.8)
- [ ] Monthly cost ceiling? (phase-wide)
- [ ] Container registry — ECR or GHCR? (task 6.10)
- [ ] Gunicorn vs Uvicorn workers behind ALB — which and how many? (task 6.3)

---

## Cross-cutting

- [ ] `structlog` output — JSON to stdout only, or also ship to a collector?
- [ ] Feature flags — none planned, or bring Unleash / GrowthBook / similar?
- [ ] `import-linter` gate (BOARD.md backlog) — schedule before Phase 2 or after?
- [ ] License for the repo — MIT, Apache-2.0, proprietary?

---

*Add questions here as they surface. Answer by editing the line to `- [x]` with the decision; promote durable decisions into `CLAUDE.md`.*
