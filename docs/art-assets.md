# HexCrawl — Pixel Asset Generation List

Derived from the domain enums (`TileType`, `BehaviourType`, `ItemType`) + `Player`.
Maps to BOARD tasks 5.2 / 5.4 / 5.5 / 5.5a.

**Pipeline (local working tooling, not in repo):** ComfyUI on CPU with an SD1.5 pixel
checkpoint + LCM LoRA (`~/src/ComfyUI`, workflow `pixel-lcm-txt2img.json`) → downscale +
4-colour quantize in Aseprite. The shared palette is committed at
[`docs/palettes/gameboy-4.gpl`](palettes/gameboy-4.gpl).

## The fixed style prefix (never change this part)

```
pixelsprite, 16-bit jrpg style, full body, front view, centered, flat shading, plain white background,
```
Append ONE subject from the tables below. Keep seed + all KSampler settings fixed across a
batch so the set stays coherent. Use `16bitscene` (not `pixelsprite`) for tiles.

---

## 1. Player — BOARD 5.4  (target ~32×32, + walk frames by hand)

| Asset | Subject to append | Notes |
|-------|-------------------|-------|
| Hero | `a knight hero in blue armor holding a sword` | The style anchor — match everything else to it. |

## 2. Enemies — BOARD 5.5  (3 archetypes, target ~32×32; boss ~48×48)

| `BehaviourType` | Subject to append | Notes |
|-----------------|-------------------|-------|
| MELEE | `a green goblin warrior with a wooden club` | Close-range grunt |
| RANGED | `a hooded skeleton archer holding a bow` | Keeps distance, shoots |
| BOSS | `a huge armored ogre boss with a spiked mace` | Bigger canvas; spawns every 5th floor (backlog) |

## 3. Items — BOARD 5.5a  (target ~16×16; generate as a SET, see tip)

| `ItemType` | Subject to append | `effect` meaning |
|------------|-------------------|------------------|
| WEAPON | `a steel sword item icon` | attack bonus |
| ARMOR | `a steel chestplate armor item icon` | defense bonus |
| SHIELD | `a round wooden shield item icon` | defense bonus |
| POTION | `a red health potion bottle item icon` | HP restored |
| KEY | `a golden key item icon` | opens doors |

> **Item tip:** generate all five in ONE pass for instant consistency —
> `pixelsprite, 16-bit jrpg style, a grid of rpg item icons, steel sword, chestplate, round shield, red potion, golden key, plain white background`
> then slice them apart in Aseprite. Items are tiny, so a shared generation beats one-by-one.

## 4. Tiles — BOARD 5.2  (16×16, MUST be seamless/tileable)

> ⚠️ **Hand-draw these in Aseprite.** AI fights hardest here: 16×16 + 4 colours + seamless
> edges is exactly where text-to-image fails. Use AI output only as a colour/shape reference,
> then redraw on a 16×16 grid. Use the `16bitscene` trigger if you do generate references.

| `TileType` | Reference subject (optional) | Notes |
|------------|------------------------------|-------|
| WALL | `16bitscene, seamless dungeon stone brick wall texture` | Must tile on all edges |
| FLOOR | `16bitscene, seamless dungeon stone floor texture` | Must tile; keep low-contrast so sprites read on top |
| STAIRS | `16bitscene, stone staircase descending, top-down` | Single tile, the descend target |
| DOOR | `16bitscene, closed wooden dungeon door` | Consider open + closed variants |

---

## Totals (v1 minimum)

- 1 player + 3 enemies + 5 items + 4 tiles = **13 base assets**
- Plus by-hand work: player walk frames, door open/closed, palette quantization on every asset.

## Workflow reminders
- Same checkpoint + same prefix + fixed seed = a matching family.
- Quantize EVERY asset to `gameboy-4.gpl` — this is what makes them look like one game.
- If style still drifts: set up IPAdapter (one hero sprite locks the whole set's style).
