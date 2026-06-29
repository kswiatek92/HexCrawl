import { describe, expect, it } from "vitest";
import type { GameStateView, TileType } from "../types/gameState";
import type { TileImages } from "./tileSet";
import { BACKGROUND_COLOR, drawFloor } from "./drawFloor";

interface DrawImageCall {
  image: unknown;
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/** A context that records the calls `drawFloor` makes, no real canvas needed. */
function fakeContext() {
  const fillRectCalls: number[][] = [];
  const drawImageCalls: DrawImageCall[] = [];
  const ctx = {
    fillStyle: "",
    fillRect(x: number, y: number, w: number, h: number) {
      fillRectCalls.push([x, y, w, h]);
    },
    drawImage(image: unknown, sx: number, sy: number, sw: number, sh: number) {
      drawImageCalls.push({ image, sx, sy, sw, sh });
    },
  };
  return { ctx, fillRectCalls, drawImageCalls };
}

/** Sentinel images keyed by type — identity is all `drawFloor` cares about. */
const IMAGES = {
  WALL: { id: "WALL" },
  FLOOR: { id: "FLOOR" },
  STAIRS: { id: "STAIRS" },
  DOOR: { id: "DOOR" },
} as unknown as TileImages;

/** Sentinel player sprite — drawn last, identity is all that's checked. */
const PLAYER = { id: "PLAYER" } as unknown as HTMLImageElement;

// 3x2 floor (smaller than the viewport → camera pins to 0,0, all 6 cells shown).
const TILES: TileType[][] = [
  ["WALL", "FLOOR", "DOOR"],
  ["FLOOR", "STAIRS", "WALL"],
];

const STATE: GameStateView = {
  player: { position: [1, 1] },
  floor: { width: 3, height: 2, tiles: TILES, stairs_down: [1, 1] },
};

describe("drawFloor", () => {
  it("clears the whole backing buffer to the backdrop first", () => {
    const { ctx, fillRectCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      STATE,
      IMAGES,
      PLAYER,
      0,
    );
    expect(ctx.fillStyle).toBe(BACKGROUND_COLOR);
    expect(fillRectCalls).toEqual([[0, 0, 240, 160]]);
  });

  it("blits one sprite per visible tile, then the player on top", () => {
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      STATE,
      IMAGES,
      PLAYER,
      0,
    );

    // 6 cells (tiles[y][x] → 16px screen pos), then the player at its tile (1,1).
    expect(drawImageCalls).toEqual([
      { image: IMAGES.WALL, sx: 0, sy: 0, sw: 16, sh: 16 },
      { image: IMAGES.FLOOR, sx: 16, sy: 0, sw: 16, sh: 16 },
      { image: IMAGES.DOOR, sx: 32, sy: 0, sw: 16, sh: 16 },
      { image: IMAGES.FLOOR, sx: 0, sy: 16, sw: 16, sh: 16 },
      { image: IMAGES.STAIRS, sx: 16, sy: 16, sw: 16, sh: 16 },
      { image: IMAGES.WALL, sx: 32, sy: 16, sw: 16, sh: 16 },
      { image: PLAYER, sx: 16, sy: 16, sw: 16, sh: 16 },
    ]);
  });

  it("shifts the player by the frame's bob offset", () => {
    // Frame 1 bobs up 1px: player y goes from 16 to 15; the tiles are unaffected.
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      STATE,
      IMAGES,
      PLAYER,
      1,
    );
    const player = drawImageCalls.at(-1);
    expect(player).toEqual({ image: PLAYER, sx: 16, sy: 15, sw: 16, sh: 16 });
  });

  it("offsets tiles and the player by the camera on a large floor", () => {
    // 80x50 floor, player mid-map → camera (33,20); world (40,25) lands at (112,80).
    const bigTiles: TileType[][] = Array.from({ length: 50 }, () =>
      Array.from({ length: 80 }, (): TileType => "FLOOR"),
    );
    bigTiles[25][40] = "STAIRS";
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      {
        player: { position: [40, 25] },
        floor: {
          width: 80,
          height: 50,
          tiles: bigTiles,
          stairs_down: [40, 25],
        },
      },
      IMAGES,
      PLAYER,
      0,
    );

    expect(drawImageCalls).toHaveLength(151); // 15x10 window + the player
    const stairs = drawImageCalls.find((c) => c.image === IMAGES.STAIRS);
    expect(stairs).toEqual({
      image: IMAGES.STAIRS,
      sx: 7 * 16,
      sy: 5 * 16,
      sw: 16,
      sh: 16,
    });
    // Player drawn last, centred in the window at the same cell the camera tracks.
    expect(drawImageCalls.at(-1)).toEqual({
      image: PLAYER,
      sx: 7 * 16,
      sy: 5 * 16,
      sw: 16,
      sh: 16,
    });
  });

  it("paints only the backdrop when there is no game state", () => {
    const { ctx, fillRectCalls, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      null,
      IMAGES,
      PLAYER,
      0,
    );
    expect(fillRectCalls).toEqual([[0, 0, 240, 160]]);
    expect(drawImageCalls).toEqual([]); // no tiles and, crucially, no player
  });
});
