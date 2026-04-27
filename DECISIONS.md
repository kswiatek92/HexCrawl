# HexCrawl — Decisions log

ADR-style log of non-obvious design choices. One entry per decision.

Format:
- **Context** — what problem / constraint prompted this
- **Decision** — what we chose
- **Alternatives considered** — what we rejected and why
- **Consequences** — what this costs us (the trade-off, honestly stated)

Entries are append-only. If a decision is reversed, add a new entry that supersedes the old one — don't edit history.

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
