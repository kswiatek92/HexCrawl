# HexCrawl — Predictions

Pre-generation predictions for non-trivial features, per `CLAUDE.md` → "Before writing non-trivial code".

Format (one section per feature):

```
## Task <id> — <title>

**Date:** YYYY-MM-DD

- **API shape:** <function vs class, signature guess>
- **Files that will change:** <list>
- **Trickiest part:** <what I expect to hurt>
- **Unknown:** <things I'm not sure about — most valuable line>

(After the plan / implementation lands, optionally add a `**Reflection:**` line:
where my prediction held up, where it missed, what I learned.)
```

Newest first.

---

## Task 1.13 — `DungeonGenerator` — BSP algorithm

**Date:** 2026-05-13

- **API shape:** Function, single call.
- **Files that will change:** new `dungeon_generator.py`, new test file, update `BOARD.md`.
- **Trickiest part:** Getting the corridor connection right. Not sure if doors get generated.
