/**
 * Item-sprite registry: maps each `ItemType` to its sprite and loads them.
 *
 * Mirrors `enemySprites.ts`. The bundled `../assets/sprites/items/*.png` are
 * transparent-background copies of the AI drafts at `assets/sprites/items/`
 * (repo root). The source of truth is those drafts plus `assets/tools/key_sprites.py`,
 * which flood-fills the opaque background to alpha so the sprite composites over the
 * floor; the PNGs here are the bundled copies so the frontend stays self-contained and
 * Vite can fingerprint them. If a draft changes, re-run the keyer to re-bake.
 *
 * Sprites are authored larger than a tile (32×32) but drawn at one tile (16×16) —
 * `GameCanvas` disables image smoothing so the downscale stays crisp (nearest-neighbour).
 *
 * Used by `drawFloor` for ground loot now; the HUD inventory (task 5.8) will reuse
 * this same registry for its item icons.
 */

import type { ItemType } from "../types/gameState";
import weaponUrl from "../assets/sprites/items/weapon.png";
import armorUrl from "../assets/sprites/items/armor.png";
import shieldUrl from "../assets/sprites/items/shield.png";
import potionUrl from "../assets/sprites/items/potion.png";
import keyUrl from "../assets/sprites/items/key.png";

/** `ItemType` → bundled sprite URL. */
export const ITEM_URLS: Record<ItemType, string> = {
  WEAPON: weaponUrl,
  ARMOR: armorUrl,
  SHIELD: shieldUrl,
  POTION: potionUrl,
  KEY: keyUrl,
};

/** Decoded item sprites, indexed by `ItemType` — what `drawFloor` blits. */
export type ItemSprites = Record<ItemType, HTMLImageElement>;

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load item sprite: ${url}`));
    img.src = url;
  });
}

/**
 * Decode all five item sprites, resolving once every image is ready.
 *
 * The renderer needs every sprite before its first paint (a half-loaded set would
 * draw gaps), so this resolves as a set rather than streaming them in.
 */
export async function loadItemSprites(): Promise<ItemSprites> {
  const types = Object.keys(ITEM_URLS) as ItemType[];
  const images = await Promise.all(
    types.map((type) => loadImage(ITEM_URLS[type])),
  );
  const result = {} as ItemSprites;
  types.forEach((type, i) => {
    result[type] = images[i];
  });
  return result;
}
