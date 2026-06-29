import { describe, expect, it } from "vitest";
import {
  BACKING_HEIGHT,
  BACKING_WIDTH,
  TILE_SIZE,
  VIEWPORT_COLS,
  VIEWPORT_ROWS,
  computeCamera,
  isWithinViewport,
  playerScreenPosition,
  visibleTiles,
  worldToScreen,
} from "./camera";

// The production floor size (QUESTIONS.md 1.5), larger than the viewport on both
// axes so the camera can actually move.
const FLOOR_W = 80;
const FLOOR_H = 50;

describe("viewport constants", () => {
  it("derives a 240x160 buffer from 15x10 tiles of 16px", () => {
    expect(BACKING_WIDTH).toBe(VIEWPORT_COLS * TILE_SIZE);
    expect(BACKING_HEIGHT).toBe(VIEWPORT_ROWS * TILE_SIZE);
    expect(BACKING_WIDTH).toBe(240);
    expect(BACKING_HEIGHT).toBe(160);
  });
});

describe("computeCamera", () => {
  it("centres on an interior player", () => {
    // half-window = floor(15/2)=7 cols, floor(10/2)=5 rows
    expect(computeCamera([40, 25], FLOOR_W, FLOOR_H)).toEqual({ x: 33, y: 20 });
  });

  it("tracks the player — a different position yields a different camera", () => {
    // Guards against a stubbed/constant camera passing the interior test.
    expect(computeCamera([50, 30], FLOOR_W, FLOOR_H)).toEqual({ x: 43, y: 25 });
  });

  it("clamps at the top-left edge", () => {
    expect(computeCamera([0, 0], FLOOR_W, FLOOR_H)).toEqual({ x: 0, y: 0 });
    // Still clamped while the player is within half a window of the edge.
    expect(computeCamera([3, 2], FLOOR_W, FLOOR_H)).toEqual({ x: 0, y: 0 });
  });

  it("clamps at the bottom-right edge", () => {
    // Window can't show past the floor: x ≤ 80-15=65, y ≤ 50-10=40.
    expect(computeCamera([79, 49], FLOOR_W, FLOOR_H)).toEqual({ x: 65, y: 40 });
  });

  it("pins to 0 when the floor is smaller than the viewport", () => {
    expect(computeCamera([2, 1], 5, 4)).toEqual({ x: 0, y: 0 });
  });
});

describe("visibleTiles", () => {
  it("returns the full 15x10 window for a large floor", () => {
    const camera = computeCamera([40, 25], FLOOR_W, FLOOR_H);
    const tiles = visibleTiles(camera, FLOOR_W, FLOOR_H);
    expect(tiles).toHaveLength(VIEWPORT_COLS * VIEWPORT_ROWS); // 150
  });

  it("maps world tiles to backing-buffer pixels relative to the camera", () => {
    const camera = { x: 33, y: 20 };
    const tiles = visibleTiles(camera, FLOOR_W, FLOOR_H);

    // Top-left of the window sits at screen (0,0) and is the camera's world cell.
    expect(tiles[0]).toEqual({
      worldX: 33,
      worldY: 20,
      screenX: 0,
      screenY: 0,
    });

    // The player's world cell (40,25) is offset (7,5) into the window → (112,80).
    const playerCell = tiles.find((t) => t.worldX === 40 && t.worldY === 25);
    expect(playerCell).toEqual({
      worldX: 40,
      worldY: 25,
      screenX: 7 * TILE_SIZE,
      screenY: 5 * TILE_SIZE,
    });
  });

  it("skips cells outside a floor smaller than the viewport", () => {
    const tiles = visibleTiles({ x: 0, y: 0 }, 5, 4);
    expect(tiles).toHaveLength(5 * 4); // only the in-bounds cells
    // No returned tile may reference a cell past the floor bounds.
    expect(tiles.every((t) => t.worldX < 5 && t.worldY < 4)).toBe(true);
  });
});

describe("worldToScreen", () => {
  it("offsets a world tile by the camera, scaled to pixels", () => {
    // Camera at (33,20): world (40,25) is (7,5) tiles into the window → (112,80).
    expect(worldToScreen({ x: 33, y: 20 }, [40, 25])).toEqual({
      x: 7 * TILE_SIZE,
      y: 5 * TILE_SIZE,
    });
  });

  it("returns an off-screen (negative) position for a tile behind the camera", () => {
    // A caller must cull these (isWithinViewport) before blitting.
    expect(worldToScreen({ x: 33, y: 20 }, [30, 18])).toEqual({
      x: -3 * TILE_SIZE,
      y: -2 * TILE_SIZE,
    });
  });
});

describe("isWithinViewport", () => {
  const camera = { x: 33, y: 20 }; // window covers x∈[33,48), y∈[20,30)

  it("accepts a tile inside the window", () => {
    expect(isWithinViewport(camera, [40, 25])).toBe(true);
  });

  it("accepts the inclusive top-left corner and rejects just outside it", () => {
    expect(isWithinViewport(camera, [33, 20])).toBe(true);
    expect(isWithinViewport(camera, [32, 20])).toBe(false);
    expect(isWithinViewport(camera, [33, 19])).toBe(false);
  });

  it("rejects the exclusive bottom-right edge", () => {
    // Last in-bounds cell is (47,29); camera.x+COLS=48 and camera.y+ROWS=30 are out.
    expect(isWithinViewport(camera, [47, 29])).toBe(true);
    expect(isWithinViewport(camera, [48, 29])).toBe(false);
    expect(isWithinViewport(camera, [47, 30])).toBe(false);
  });
});

describe("playerScreenPosition", () => {
  it("puts a centred player at the middle of the window", () => {
    // Interior player → camera (33,20); offset (7,5) into the window.
    const camera = computeCamera([40, 25], FLOOR_W, FLOOR_H);
    expect(playerScreenPosition(camera, [40, 25])).toEqual({
      x: 7 * TILE_SIZE,
      y: 5 * TILE_SIZE,
    });
  });

  it("drifts the player off-centre when the camera clamps at an edge", () => {
    // Bottom-right corner: camera pins to (65,40), so the player sits deep into
    // the window rather than centred — (79-65, 49-40) = (14, 9) tiles.
    const camera = computeCamera([79, 49], FLOOR_W, FLOOR_H);
    expect(playerScreenPosition(camera, [79, 49])).toEqual({
      x: 14 * TILE_SIZE,
      y: 9 * TILE_SIZE,
    });
  });
});
