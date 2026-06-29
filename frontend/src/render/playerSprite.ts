/**
 * Player-sprite loader.
 *
 * The bundled `../assets/sprites/player.png` is a transparent-background copy of the
 * AI draft at `assets/sprites/player/player.png` (repo root). The source of truth is
 * that draft plus `assets/tools/key_sprites.py`, which flood-fills the draft's opaque
 * background to alpha so the sprite composites over the floor; the PNG here is the
 * bundled copy so the frontend stays self-contained and Vite can fingerprint it. If
 * the draft changes, re-run the keyer to re-bake this file.
 *
 * Mirrors `tileSet.ts`'s load pattern. The sprite is authored at 32×32 but drawn at
 * one tile (16×16) — `GameCanvas` disables image smoothing so the downscale stays
 * crisp (nearest-neighbour).
 */

import playerUrl from "../assets/sprites/player.png";

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () =>
      reject(new Error(`Failed to load player sprite: ${url}`));
    img.src = url;
  });
}

/** Decode the player sprite, resolving once it is ready to blit. */
export function loadPlayerSprite(): Promise<HTMLImageElement> {
  return loadImage(playerUrl);
}
