# HexCrawl — Decisions log

ADR-style log of non-obvious design choices. One entry per decision.

Format:
- **Context** — what problem / constraint prompted this
- **Decision** — what we chose
- **Alternatives considered** — what we rejected and why
- **Consequences** — what this costs us (the trade-off, honestly stated)

Entries are append-only. If a decision is reversed, add a new entry that supersedes the old one — don't edit history.

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
