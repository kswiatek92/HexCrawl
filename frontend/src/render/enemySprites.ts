/**
 * Enemy-sprite registry: maps each `BehaviourType` to its sprite and loads them.
 *
 * Mirrors `tileSet.ts`. The bundled `../assets/sprites/enemies/*.png` are
 * transparent-background copies of the AI drafts at `assets/sprites/enemies/`
 * (repo root). The source of truth is those drafts plus `assets/tools/key_sprites.py`,
 * which flood-fills the opaque background to alpha so the sprite composites over the
 * floor; the PNGs here are the bundled copies so the frontend stays self-contained and
 * Vite can fingerprint them. If a draft changes, re-run the keyer to re-bake.
 *
 * Sprites are authored larger than a tile (melee/ranged 32×32, boss 48×48) but drawn
 * at one tile (16×16) — `GameCanvas` disables image smoothing so the downscale stays
 * crisp (nearest-neighbour).
 */

import type { BehaviourType } from "../types/gameState";
import meleeUrl from "../assets/sprites/enemies/melee.png";
import rangedUrl from "../assets/sprites/enemies/ranged.png";
import bossUrl from "../assets/sprites/enemies/boss.png";

/** `BehaviourType` → bundled sprite URL. */
export const ENEMY_URLS: Record<BehaviourType, string> = {
  MELEE: meleeUrl,
  RANGED: rangedUrl,
  BOSS: bossUrl,
};

/** Decoded enemy sprites, indexed by `BehaviourType` — what `drawFloor` blits. */
export type EnemySprites = Record<BehaviourType, HTMLImageElement>;

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () =>
      reject(new Error(`Failed to load enemy sprite: ${url}`));
    img.src = url;
  });
}

/**
 * Decode all three enemy sprites, resolving once every image is ready.
 *
 * The renderer needs every sprite before its first paint (a half-loaded set would
 * draw gaps), so this resolves as a set rather than streaming them in.
 */
export async function loadEnemySprites(): Promise<EnemySprites> {
  const behaviours = Object.keys(ENEMY_URLS) as BehaviourType[];
  const images = await Promise.all(
    behaviours.map((behaviour) => loadImage(ENEMY_URLS[behaviour])),
  );
  const result = {} as EnemySprites;
  behaviours.forEach((behaviour, i) => {
    result[behaviour] = images[i];
  });
  return result;
}
