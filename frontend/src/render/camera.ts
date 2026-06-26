/**
 * Viewport geometry + camera math for the canvas renderer.
 *
 * Pure module — no DOM, no canvas. This is the load-bearing "where do we look"
 * logic the imperative draw step (`drawFloor`) and the React component
 * (`GameCanvas`) both build on, kept framework-free so it is fully unit-testable.
 *
 * Rendering model (QUESTIONS.md:114): a fixed 240×160 GBA-native backing buffer
 * of 16px tiles → a 15×10 tile window. The floor (80×50) dwarfs the window, so
 * the camera follows the player: we draw a 15×10 slice centred on the player and
 * clamped to stay inside the floor.
 */

import type { Position } from "../types/gameState";

/** Edge length of one tile in the backing buffer, in pixels. */
export const TILE_SIZE = 16;
/** Viewport width in tiles (240 / 16). */
export const VIEWPORT_COLS = 15;
/** Viewport height in tiles (160 / 16). */
export const VIEWPORT_ROWS = 10;
/** Backing-buffer width in pixels (GBA-native). */
export const BACKING_WIDTH = VIEWPORT_COLS * TILE_SIZE; // 240
/** Backing-buffer height in pixels (GBA-native). */
export const BACKING_HEIGHT = VIEWPORT_ROWS * TILE_SIZE; // 160
/** Integer upscale factor for crisp pixels (240×160 → 720×480). */
export const SCALE = 3;

/** Top-left tile of the viewport, in floor (world) tile coordinates. */
export interface Camera {
  x: number;
  y: number;
}

/** One tile to draw: its world coords and where it lands in the backing buffer. */
export interface VisibleTile {
  worldX: number;
  worldY: number;
  screenX: number;
  screenY: number;
}

/**
 * Clamp `value` into `[min, max]`. When `max < min` (the floor is smaller than
 * the viewport on this axis) the window can't move, so pin to `min` (0).
 */
function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.max(min, Math.min(value, max));
}

/**
 * The viewport's top-left tile, centred on the player and clamped to the floor.
 *
 * Centring puts the player at `floor(cols/2)` from the left edge of the window;
 * clamping keeps the window from showing past the floor's edges, so the player
 * drifts off-centre near the borders (classic roguelike camera).
 */
export function computeCamera(
  player: Position,
  floorWidth: number,
  floorHeight: number,
): Camera {
  const [px, py] = player;
  const x = clamp(
    px - Math.floor(VIEWPORT_COLS / 2),
    0,
    floorWidth - VIEWPORT_COLS,
  );
  const y = clamp(
    py - Math.floor(VIEWPORT_ROWS / 2),
    0,
    floorHeight - VIEWPORT_ROWS,
  );
  return { x, y };
}

/**
 * The tiles inside the viewport, each with its backing-buffer pixel position.
 *
 * Walks the 15×10 window from the camera's top-left. Cells that fall outside the
 * floor (only possible when a floor is smaller than the viewport) are skipped, so
 * a caller can blindly draw every returned tile without a bounds check.
 */
export function visibleTiles(
  camera: Camera,
  floorWidth: number,
  floorHeight: number,
): VisibleTile[] {
  const tiles: VisibleTile[] = [];
  for (let row = 0; row < VIEWPORT_ROWS; row++) {
    for (let col = 0; col < VIEWPORT_COLS; col++) {
      const worldX = camera.x + col;
      const worldY = camera.y + row;
      if (worldX < 0 || worldX >= floorWidth) continue;
      if (worldY < 0 || worldY >= floorHeight) continue;
      tiles.push({
        worldX,
        worldY,
        screenX: col * TILE_SIZE,
        screenY: row * TILE_SIZE,
      });
    }
  }
  return tiles;
}
