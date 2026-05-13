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
- [x] HP / damage scaling across floors — linear, exponential, hand-authored tables? → **Linear** for v1. Predictable TTK, easier to balance; the scaling function can be swapped later without touching the `Enemy` dataclass. Floor-1 melee damage cap of 1 HP/hit still holds.
- [x] Ranged enemies: which tile types block line-of-sight? (walls only? doors?) → **`WALL` and closed `DOOR` block LOS.** Rule: "solid, IRL view-blocking" tiles block. `FLOOR` and `STAIRS` do not. Future blockers (smoke, tall grass, pillars) slot in as new tile types without changing the rule.
- [x] Boss cadence — every 5th floor (per Backlog in BOARD.md) or something else for v1? → **Every 5th floor** (floors 5, 10, 15, …), matching the Backlog entry.
- [x] Does `BehaviourType` start as `MELEE | RANGED | BOSS` exactly, or more granular (e.g. `MELEE_AGGRESSIVE`, `MELEE_COWARD`)? → **`MELEE | RANGED | BOSS`** for v1, matching CLAUDE.md's Key Domain Concepts verbatim. Granular variants (`MELEE_COWARD`, etc.) are cheap to add in v2 — nothing else in the domain pattern-matches on the enum yet.

### Item + ItemType (task 1.4)
- [x] Which item types ship in v1? (potions, weapons, armor, scrolls, gold, keys?) → **`WEAPON | ARMOR | SHIELD | POTION | KEY`**. Each maps to an existing Player slot: weapon/armor/shield to their dedicated slots; POTION and KEY both live in the `consumables` stack (cap 5 total). Scrolls / gold deferred to v2.
- [x] Stackable items — flat count on one instance, or many instances? → **Flat `count: int = 1` on the `Item` instance.** Stackable types (`POTION`, `KEY`) merge into one instance on pickup; non-stackable types (`WEAPON`, `ARMOR`, `SHIELD`) always have `count=1`. Consumables stack is a list of ≤5 `Item` instances.
- [x] Item multiplier for scoring — per-type weight, per-rarity, or per-item value? → **Per-type weight.** Static `ItemType → float` map owned by `ScoreService` (exact values TBD during task 1.7). Rarity / per-item overrides can layer in later without breaking the contract.

### Floor (task 1.5)
- [x] Grid dimensions — fixed (e.g. 80×50) or scales with floor index? → **`80×50` fixed for v1.** Classic roguelike standard (Rogue, NetHack); enough room for 6–10 BSP rooms. May scale with floor index later — revisit once `DungeonGenerator` exists.
- [x] One down-staircase per floor, or multiple branches? → **One down-staircase per floor.** Linear descent for v1; branching deferred.
- [x] Do items and enemies live on the `Floor` or in separate collections keyed by position? → **Mixed, deliberately**: `enemies: list[Enemy]` (quiz-aligned — `Enemy.position` is intrinsic, so no key needed; ~5–20 enemies per floor makes O(n) lookup a non-issue for v1) and `items: dict[tuple[int, int], list[Item]]` (necessary — `Item` has no intrinsic position, so the dict key is canonical; list value supports stacking). Reverses the earlier dict-for-both answer after the [QUIZZES.md Q4 design intent](QUIZZES.md#L60) was surfaced. Worth a `DECISIONS.md` entry once `GameService` starts moving items between `Floor.items` and `Player`'s slots — that's where the asymmetry will bite.

### Dungeon (task 1.6)
- [x] Total depth — fixed (e.g. 20 floors) or endless? → **100 floors, fixed** for v1. Finite depth gives a concrete "win" state and caps run length for leaderboard fairness; endless mode deferred.
- [x] Seed source — client-provided, server-random, or both (daily seed mode)? → **Both.** Server-random for normal runs (fresh seed per `StartGame`); client-provided for daily/weekly leaderboard modes where every player gets the same static seed for fair comparison. The `seed: int` field stays the same shape — only the caller picks.
- [x] Is the player ref stored on `Dungeon` or passed separately to services? → **Passed separately** (Option B). `Dungeon` holds `dungeon_id`, `seed`, `floors`, `current_floor_index` — no `player` field. Services take both: `process_turn(dungeon, player, action)`. Accepted trade-off: more plumbing per signature now, but Player stays "who the user is" (future profile/unlocks persistent across runs) while Dungeon stays "this specific run" — co-op in v2 is additive, not a refactor. **Note:** this deviates from the [QUIZZES.md Task 1.6 Q3](QUIZZES.md#L69) hint ("Dungeon contains a Player") — the quiz wording may need updating, or the Q3 answer will accept that v1 chose the non-hinted shape deliberately.

### Score (task 1.7)
- [x] Exact formula — literally `floors × kills × item_multiplier`, or weighted (e.g. `floors² × kills × item_multiplier`)? → **Weighted on floors.** Depth dominates so descending is strictly better than grinding shallow floors. Exponent fixed at `floors_reached**2` (locked by ADR 0002 in `DECISIONS.md`).
- [x] Penalties for damage taken, turns used, or deaths? → **Damage-taken penalty** only. Rewards careful play; discourages tank-and-grind. Requires a cumulative `damage_taken` counter on the run state (likely `Player` or `Dungeon` — exact home TBD during implementation). Turns-used penalty deferred; deaths is a no-op in v1 (permadeath = one death per run).
- [x] Minimum floor for a score to count at all? → **Kill-based threshold** instead of floor-based: a run must have **≥ 5 kills** to qualify for the leaderboard (tentative — tune after playtesting). Measures actual engagement rather than just walking. Where the check lives is TBD: likely in `SubmitScore` (Phase 3) or the leaderboard query, not in `ScoreService.compute()` — keeps domain flexible.

### TileType (task 1.8)
- [x] Tiles beyond `WALL | FLOOR | STAIRS | DOOR`? (trap, water, chest, altar?) → **No additional tiles for v1.** Ship `WALL | FLOOR | STAIRS | DOOR` only — matches CLAUDE.md "Key Domain Concepts". `StrEnum` makes future variants (`TRAP`, `WATER`, `CHEST`, `ALTAR`) additive without breaking existing pattern matches.

### Action (task 1.9)
- [x] Actions beyond Move/Attack/UseItem/Descend/Abandon? Likely candidates: `Wait`, `PickUp`, `DropItem`, `Open` (door), `Equip`. → **Ship v1 with `Move | Attack | UseItem | Descend | Abandon | Wait | PickUp | Open`.** `Wait` (skip turn — needed in turn-based combat for regen/enemy-advance), `PickUp` (items live in `Floor.items` dict per the 1.5 decision; explicit pickup lets the player step over without auto-grabbing into a full slot), `Open` (closed `DOOR` blocks LOS per the 1.3 decision, so opening must be a discrete action). **Defer** `DropItem` (no general bag — slots auto-drop on replace per the 1.2 decision) and `Equip` (pickup goes straight into the slot, so no separate equip step in v1).
- [x] Is `Attack` implicit on `Move into enemy tile`, or a separate explicit action? → **Implicit.** Moving into an enemy-occupied tile resolves as an attack; no separate `Attack` action variant needs a target field. Keeps the input surface minimal (movement keys do double duty) and matches classic roguelike feel (Rogue, NetHack, DCSS). The `Attack` variant still exists in the union for future ranged/targeted actions and for explicit attack-without-move (e.g. attacking a diagonal tile from a position where moving there is blocked).

### DungeonGenerator (task 1.13)
- [x] BSP parameters — min room size, max recursion depth, corridor style (L-shape / straight)? → **Min room 4×4, max recursion depth 5, L-shape corridors.** 4×4 is the smallest room that admits a 1-tile-wide corridor entry on each side without degenerating into a single-tile cell. Depth 5 caps leaf rooms at 32, comfortably above the 6–10 target rooms for an 80×50 floor — picking a tighter cap risks under-partitioning, a looser one fragments the map. L-shape corridors (two straight segments meeting at a right angle) are the classic roguelike read on a tile grid and survive the inevitable case where BSP partitions don't line up; pure-straight corridors would fail too often given non-aligned partitions. The exact min-size and depth values are tunable knobs on `DungeonGenerator` — **not** baked-in constants — so playtesting can adjust without an algorithm rewrite.
- [x] Post-gen reachability check — enforce or trust the algorithm? → **Enforce** via flood-fill from the spawn tile after generation. BSP only *probabilistically* yields full connectivity once corridors are stitched in — bugs in the corridor pass produce orphan rooms that are nightmarish to debug post-hoc (player gets stuck, can't find stairs, leaderboard runs invalidated). Flood-fill is O(W·H) ≈ 4 000 ops on an 80×50 grid — negligible — and stays pure, so it's trivially seeded-equality testable. If unreachable tiles are detected, the generator should re-roll (with a bumped sub-seed) rather than silently patching, so the failure mode is "regen takes a few extra ms" rather than "weird half-broken floor."
- [x] Enemy / item placement — part of this generator or a separate step? → **Separate step**: `DungeonGenerator` produces pure geometry (`Floor` with tiles + stairs position only), and a downstream `populate_floor(floor, depth, rng) -> Floor` function adds enemies and items. This keeps the generator's contract narrow — "given a seed and floor index, produce a deterministic layout" — and makes seeded-equality testing of *layout* possible without entangling enemy/item RNG draws. It also decouples balance tuning (spawn density curves, drop tables, boss cadence) from algorithmic changes to the layout — you can re-tune Phase 4 of v1 without touching the BSP pass. Both functions take the same RNG (or split sub-RNGs from the parent seed) so the run remains fully reproducible.

### EnemyAI (task 1.15)
- [x] Line-of-sight gating, or blind Manhattan pathing? → **LOS-gated** for v1. Blind Manhattan pathing produces enemies that "know" the player's position through walls — visually wrong and feels unfair (the kind of thing players notice within five turns). LOS gating is the standard roguelike contract and aligns with the [task 1.3 decision](#enemy--behaviourtype-task-13) that `WALL` and closed `DOOR` block line of sight, so the same predicate that gates ranged attacks gates AI awareness — one rule, one mental model. Stealth-around-corners falls out of this for free.
- [x] FOV algorithm if LOS is needed — shadowcasting, raycasting, symmetric-shadowcasting? → **Symmetric shadowcasting.** Modern roguelikedev consensus pick (NetHack/DCSS-class projects use it). Two properties that matter: (1) **symmetric** — if the AI sees the player, the player sees the AI, so the rendering layer and the AI layer can share a single FOV pass without "I see them but they don't see me" bugs that break combat fairness; (2) **artifact-free at corners** — classic recursive shadowcasting has known corner-leak bugs, Bresenham raycasting has the asymmetry bug. Implementation is ~80 lines of pure code; lives in `domain/services/fov.py` so it stays adapter-free.
- [x] Wake-up radius — enemies chase always, or only when within N tiles? → **Within 8 tiles AND in LOS.** Combined predicate: `chebyshev_distance(enemy, player) <= 8 AND has_los(enemy, player)`. 8 is roguelike-standard (NetHack-ish) and corresponds roughly to one small-room diameter in Chebyshev distance — meaning enemies wake when the player enters their room/corridor segment but not from across the whole floor. The LOS half rewards stealth approach (slipping past a corridor while staying behind a wall), the radius half prevents enemies from chasing across the entire 80×50 grid the moment the player has any sightline. Once awoken, an enemy stays awoken for the rest of the floor — losing aggro after one missed turn would be too lenient and would cause oscillating chase/sleep behaviour at the LOS boundary.

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

- [x] `structlog` output — JSON to stdout only, or also ship to a collector? → **JSON to stdout only for v1.** Twelve-factor compliant: the runtime emits structured logs to stdout, the *platform* (Docker / ECS / journald) decides where they go. This means swapping the collector — CloudWatch Logs in Phase 6, Loki/Grafana later, Datadog if the project ever needs it — is a *deploy-config* change with **zero application code changes**. Pre-wiring a specific collector now would couple the domain/adapter layers to a transport choice that's almost certain to change, and would make local dev (where you just want `docker compose logs -f api`) painfully indirect. Decision is reversible — the moment a collector is needed, add a sidecar or processor.
- [x] Feature flags — none planned, or bring Unleash / GrowthBook / similar? → **None for v1.** This is a single-developer portfolio project: no rollout cohorts, no A/B testing, no multi-tenant gating, no need to dark-launch a feature behind a kill switch. Adding a flag system before there's anything to flag is premature infrastructure — it adds a dependency, a service to run locally, an environment variable surface, and a layer of indirection on every gated branch, in exchange for zero current value. Re-evaluate **only** if a concrete need surfaces (e.g. shipping a major rule change without breaking existing leaderboard runs) — and even then, the simplest flag system is a Postgres table + a `feature_enabled(name)` adapter, not a full SaaS.
- [x] `import-linter` gate (BOARD.md backlog) — schedule before Phase 2 or after? → **Before Phase 2.** Phase 2 is the first moment a hexagonal violation can plausibly slip in: adapters land (`PostgresGameRepository`, `RedisCache`), and the temptation to import them upward — or to leak `sqlalchemy` types into a domain dataclass field — becomes real. Adding the gate **at the Phase 1 → Phase 2 boundary** catches the first risky PR rather than letting violations accumulate and audit-debt build up. The setup cost is small (one config file + one CI step), and it codifies the architectural rule into a hard CI failure rather than a code-review ask. Do this as the first task of Phase 2 (or a Phase 1.5 chore). Retrofitting later means reading every existing import to confirm clean state, which is the same work plus the risk of having to refactor.
- [x] License for the repo — MIT, Apache-2.0, proprietary? → **MIT.** Simplest permissive license, zero ambiguity, standard for portfolio projects. Matches the framing in `CLAUDE.md` ("HexCrawl is a vehicle for learning… portfolio centrepiece") — the goal is for others to *be able* to read, fork, learn from, and reuse this code. **Not Apache-2.0** because there are no patents to grant and the extra notice requirements add friction with no benefit at this scale. **Not proprietary** because closed-source hostile-licensing actively undermines the "show this off, let people learn from it" goal. Add `LICENSE` file at repo root with the standard MIT text + copyright line. Reversible later if the project ever pivots to commercial use, but the pivot is unlikely.
- [ ] Per-turn CPU budget — at what wall-clock cost does a `process_turn` step stop being "inline on the event loop" and become a Celery candidate? `DECISIONS.md` ADR-0003 currently uses a placeholder of ~5 ms as the threshold; needs to be substantiated (or replaced) by real profiling once the WS turn loop is wired up. Open questions inside this: do we measure p50, p95, or worst-case? Per turn or per session-second? Is the budget different for boss floors / floor 10+ where BSP regen may be more frequent? Decision should land before Phase 4 (`map_generation` task), because that's the first time we'll concretely choose what to push off the loop.

---

*Add questions here as they surface. Answer by editing the line to `- [x]` with the decision; promote durable decisions into `CLAUDE.md`.*
