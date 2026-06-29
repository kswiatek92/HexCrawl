/**
 * Imperative paint step: draw one frame of the floor into the backing buffer.
 *
 * Everything is injected (context, state, images) so the function is a pure
 * transform of inputs → canvas calls, with no DOM lookups or globals of its own.
 * That keeps it testable with a recording fake context and keeps the "what to
 * draw" math (in `camera.ts`) separate from the "how to draw" calls here.
 *
 * 5.3 drew floor tiles only. 5.4 adds the player sprite on top, at its tile with a
 * frame-driven idle bob; 5.5 adds enemies and 5.5a ground items over the same camera.
 */

import type { GameStateView, Position } from "../types/gameState";
import type { TileImages } from "./tileSet";
import type { EnemySprites } from "./enemySprites";
import type { ItemSprites } from "./itemSprites";
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
 * Clear the buffer to the backdrop, then blit the visible floor slice, ground
 * items, enemies, and the player (in that painter's order).
 *
 * Clearing every frame avoids smearing stale pixels as the camera moves, and
 * fills the border gap when the floor is smaller than the viewport. A `null`
 * state (no run yet — live data arrives in task 5.6) paints just the backdrop.
 *
 * Ground items are drawn first over the floor, then enemies, then the player — so
 * actors stand on top of loot. Items and enemies both sit anywhere on the 80×50
 * floor, so each is culled if off-screen. The player is drawn last (on top of
 * everything) at its tile, scaled to one cell; `frame` selects the idle-bob
 * vertical offset so the loop can animate it.
 */
export function drawFloor(
  ctx: CanvasRenderingContext2D,
  gameState: GameStateView | null,
  images: TileImages,
  playerSprite: HTMLImageElement,
  enemySprites: EnemySprites,
  itemSprites: ItemSprites,
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

  // Ground items, before actors so the player/enemies stand on top of loot. The
  // key is the stringified tile ("x,y"); a tile can hold several stacks, but only
  // one 16px sprite fits the cell, so we draw the first (representative) item.
  for (const [key, stack] of Object.entries(floor.items)) {
    if (stack.length === 0) continue;
    const [kx, ky] = key.split(",");
    const position: Position = [Number(kx), Number(ky)];
    if (!isWithinViewport(camera, position)) continue;
    const { x, y } = worldToScreen(camera, position);
    ctx.drawImage(itemSprites[stack[0].item_type], x, y, TILE_SIZE, TILE_SIZE);
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
