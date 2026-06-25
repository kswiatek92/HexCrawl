# HexCrawl — Sprite assets

Pixel-art sprites for the Phase 5 frontend. **All are AI-generated drafts** (local CPU
ComfyUI + SD1.5 pixel checkpoint), downscaled and quantized to the shared 4-colour Game
Boy palette ([`docs/palettes/gameboy-4.gpl`](../docs/palettes/gameboy-4.gpl)). Treat them
as placeholders good enough to build and test the renderer against — polish or replace
before v1.

## Layout (named by domain enum)

Files are named after the enum values the backend sends over the WebSocket, so the
renderer can resolve a sprite directly from game state — no name mapping needed:

```
assets/sprites/
├── player/player.png              # the hero (32×32)
├── enemies/{melee,ranged,boss}.png   # BehaviourType (32×32; boss 48×48)
├── items/{weapon,armor,shield,potion,key}.png   # ItemType (32×32)
└── tiles/{wall,floor,door}.png    # TileType (16×16)   — STAIRS missing, see below
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

- **`tiles/stairs.png` — missing.** SD1.5 can't generate a staircase tile; hand-draw it
  in Aseprite (a few diagonal steps on a 16×16 grid). `STAIRS.status = "todo"` in the manifest.
- **`rough` assets** (skeleton/ranged, armor, door) read acceptably but aren't ideal —
  redraw or re-roll when you have time.
- **Tiles not verified seamless** — `wall`/`floor` are textures, not guaranteed to tile
  edge-to-edge; fix the edges in Aseprite if seams show in the renderer.

## Regenerating

The pipeline lives in `~/pixelart/` (not in this repo): `generate_all.py` (full set),
`reroll.py` (corrected prompts), `variants.py` (seed cherry-pick). They drive the local
ComfyUI API + Aseprite CLI. Prompts and the generation playbook are in
[`docs/art-assets.md`](../docs/art-assets.md).
