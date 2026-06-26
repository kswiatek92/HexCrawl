# HexCrawl — Sprite assets

Pixel-art sprites for the Phase 5 frontend. The player/enemy/item sprites are **AI-generated
drafts** (local CPU ComfyUI + SD1.5 pixel checkpoint); the **`tiles/` are hand-authored** by
[`tools/gen_tiles.py`](tools/gen_tiles.py). Everything sits in the shared 4-colour Game Boy
palette ([`docs/palettes/gameboy-4.gpl`](../docs/palettes/gameboy-4.gpl)). Treat the AI drafts
as placeholders good enough to build and test the renderer against — polish or replace before v1.

## Layout (named by domain enum)

Files are named after the enum values the backend sends over the WebSocket, so the
renderer can resolve a sprite directly from game state — no name mapping needed:

```
assets/sprites/
├── player/player.png              # the hero (32×32)
├── enemies/{melee,ranged,boss}.png   # BehaviourType (32×32; boss 48×48)
├── items/{weapon,armor,shield,potion,key}.png   # ItemType (32×32)
└── tiles/{wall,floor,stairs,door}.png   # TileType (16×16) — hand-authored, see below
```

[`manifest.json`](manifest.json) maps every enum → sprite path, pixel size, and a
`status` (`draft` = usable, `rough` = reads ok but worth redrawing, `todo` = missing).
Load it in the frontend instead of hard-coding paths.

## Consumes-by (BOARD tasks)

| Task | Uses |
|------|------|
| 5.2 Tile set | `tiles/*` |
| 5.3 Canvas renderer | `manifest.json` + all sprites |
| 5.4 Player sprite | `player/player.png` |
| 5.5 Enemy sprites | `enemies/*` |
| 5.5a Item sprites | `items/*` |

## Known gaps / TODO

- **Tiles are hand-authored, not AI** (task 5.2). `wall/floor/stairs/door.png` are produced by
  [`tools/gen_tiles.py`](tools/gen_tiles.py) — palette-pure and seamless by construction
  (`wall`/`floor` tile edge-to-edge; covered by `tests/unit/assets/test_tile_set.py`). Re-tune by
  editing the pixel grids in that script and re-running `python assets/tools/gen_tiles.py`.
- **`rough` assets** (skeleton/ranged, armor) read acceptably but aren't ideal — redraw or
  re-roll when you have time.

## Regenerating

The pipeline lives in `~/pixelart/` (not in this repo): `generate_all.py` (full set),
`reroll.py` (corrected prompts), `variants.py` (seed cherry-pick). They drive the local
ComfyUI API + Aseprite CLI. Prompts and the generation playbook are in
[`docs/art-assets.md`](../docs/art-assets.md).
