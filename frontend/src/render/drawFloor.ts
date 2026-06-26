/**
 * Imperative paint step: draw one frame of the floor into the backing buffer.
 *
 * Everything is injected (context, state, images) so the function is a pure
 * transform of inputs → canvas calls, with no DOM lookups or globals of its own.
 * That keeps it testable with a recording fake context and keeps the "what to
 * draw" math (in `camera.ts`) separate from the "how to draw" calls here.
 *
 * 5.3 draws floor tiles only. Player / enemy / item sprites are tasks
 * 5.4 / 5.5 / 5.5a — the camera centres on the player, but no actor is painted.
 */

import type { GameStateView } from "../types/gameState";
import type { TileImages } from "./tileSet";
import {
  BACKING_HEIGHT,
  BACKING_WIDTH,
  TILE_SIZE,
  computeCamera,
  visibleTiles,
} from "./camera";

/** Darkest Game Boy DMG palette colour — the empty/out-of-view backdrop. */
export const BACKGROUND_COLOR = "#0F380F";

/**
 * Clear the buffer to the backdrop, then blit the visible slice of the floor.
 *
 * Clearing every frame avoids smearing stale pixels as the camera moves, and
 * fills the border gap when the floor is smaller than the viewport. A `null`
 * state (no run yet — live data arrives in task 5.6) paints just the backdrop.
 */
export function drawFloor(
  ctx: CanvasRenderingContext2D,
  gameState: GameStateView | null,
  images: TileImages,
): void {
  ctx.fillStyle = BACKGROUND_COLOR;
  ctx.fillRect(0, 0, BACKING_WIDTH, BACKING_HEIGHT);

  if (gameState === null) return;

  const { floor, player } = gameState;
  const camera = computeCamera(player.position, floor.width, floor.height);
  for (const tile of visibleTiles(camera, floor.width, floor.height)) {
    const type = floor.tiles[tile.worldY][tile.worldX];
    ctx.drawImage(
      images[type],
      tile.screenX,
      tile.screenY,
      TILE_SIZE,
      TILE_SIZE,
    );
  }
}
