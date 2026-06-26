/**
 * Tile-image registry: maps each `TileType` to its sprite and loads them.
 *
 * The four 16×16 GBA-palette tiles are the hand-authored set from task 5.2. The
 * **source of truth** is `assets/tools/gen_tiles.py` at the repo root (verified
 * palette-pure + seamless by `tests/unit/assets/test_tile_set.py`); the PNGs in
 * `../assets/tiles/` are bundled copies so the frontend stays self-contained and
 * Vite can fingerprint them. If the generator changes, re-copy the four files.
 */

import type { TileType } from "../types/gameState";
import wallUrl from "../assets/tiles/wall.png";
import floorUrl from "../assets/tiles/floor.png";
import stairsUrl from "../assets/tiles/stairs.png";
import doorUrl from "../assets/tiles/door.png";

/** `TileType` → bundled sprite URL. */
export const TILE_URLS: Record<TileType, string> = {
  WALL: wallUrl,
  FLOOR: floorUrl,
  STAIRS: stairsUrl,
  DOOR: doorUrl,
};

/** Decoded tile sprites, indexed by `TileType` — what `drawFloor` blits. */
export type TileImages = Record<TileType, HTMLImageElement>;

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load tile sprite: ${url}`));
    img.src = url;
  });
}

/**
 * Decode all four tile sprites, resolving once every image is ready.
 *
 * The renderer needs every tile before its first paint (a half-loaded set would
 * draw gaps), so this resolves as a set rather than streaming them in.
 */
export async function loadTileImages(): Promise<TileImages> {
  const types = Object.keys(TILE_URLS) as TileType[];
  const images = await Promise.all(
    types.map((type) => loadImage(TILE_URLS[type])),
  );
  const result = {} as TileImages;
  types.forEach((type, i) => {
    result[type] = images[i];
  });
  return result;
}
