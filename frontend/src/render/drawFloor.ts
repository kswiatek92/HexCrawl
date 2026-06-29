/**
 * Imperative paint step: draw one frame of the floor into the backing buffer.
 *
 * Everything is injected (context, state, images) so the function is a pure
 * transform of inputs → canvas calls, with no DOM lookups or globals of its own.
 * That keeps it testable with a recording fake context and keeps the "what to
 * draw" math (in `camera.ts`) separate from the "how to draw" calls here.
 *
 * 5.3 drew floor tiles only. 5.4 adds the player sprite on top, at its tile with a
 * frame-driven idle bob; enemies / items are tasks 5.5 / 5.5a over the same camera.
 */

import type { GameStateView } from "../types/gameState";
import type { TileImages } from "./tileSet";
import type { EnemySprites } from "./enemySprites";
import {
  BACKING_HEIGHT,
  BACKING_WIDTH,
  TILE_SIZE,
  computeCamera,
  isWithinViewport,
  playerScreenPosition,
  visibleTiles,
  worldToScreen,
} from "./camera";
import { bobOffsetForFrame } from "./playerAnimation";

/** Darkest Game Boy DMG palette colour — the empty/out-of-view backdrop. */
export const BACKGROUND_COLOR = "#0F380F";

/**
 * Clear the buffer to the backdrop, blit the visible floor slice, then the player.
 *
 * Clearing every frame avoids smearing stale pixels as the camera moves, and
 * fills the border gap when the floor is smaller than the viewport. A `null`
 * state (no run yet — live data arrives in task 5.6) paints just the backdrop.
 *
 * Enemies are drawn after the floor, each at its tile (one cell) and culled if
 * off-screen — they can sit anywhere on the 80×50 floor. The player is drawn last
 * (on top of floor and enemies) at its tile, scaled to one cell; `frame` selects the
 * idle-bob vertical offset so the loop can animate it.
 */
export function drawFloor(
  ctx: CanvasRenderingContext2D,
  gameState: GameStateView | null,
  images: TileImages,
  playerSprite: HTMLImageElement,
  enemySprites: EnemySprites,
  frame: number,
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

  for (const enemy of floor.enemies) {
    if (!isWithinViewport(camera, enemy.position)) continue;
    const { x, y } = worldToScreen(camera, enemy.position);
    ctx.drawImage(enemySprites[enemy.behaviour], x, y, TILE_SIZE, TILE_SIZE);
  }

  const { x, y } = playerScreenPosition(camera, player.position);
  ctx.drawImage(
    playerSprite,
    x,
    y + bobOffsetForFrame(frame),
    TILE_SIZE,
    TILE_SIZE,
  );
}
