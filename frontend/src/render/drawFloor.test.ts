import { describe, expect, it } from "vitest";
import type { GameStateView, TileType } from "../types/gameState";
import type { TileImages } from "./tileSet";
import type { EnemySprites } from "./enemySprites";
import type { ItemSprites } from "./itemSprites";
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

/** Sentinel enemy sprites keyed by behaviour — identity is all that's checked. */
const ENEMIES = {
  MELEE: { id: "MELEE" },
  RANGED: { id: "RANGED" },
  BOSS: { id: "BOSS" },
} as unknown as EnemySprites;

/** Sentinel item sprites keyed by item type — identity is all that's checked. */
const ITEMS = {
  WEAPON: { id: "WEAPON" },
  ARMOR: { id: "ARMOR" },
  SHIELD: { id: "SHIELD" },
  POTION: { id: "POTION" },
  KEY: { id: "KEY" },
} as unknown as ItemSprites;

/** A PlayerView at a tile — drawFloor reads only `position`; stats are filler. */
const playerAt = (x: number, y: number): GameStateView["player"] => ({
  name: "Hero",
  position: [x, y],
  hp: 20,
  max_hp: 20,
  attack: 3,
  defense: 1,
});

// 3x2 floor (smaller than the viewport → camera pins to 0,0, all 6 cells shown).
const TILES: TileType[][] = [
  ["WALL", "FLOOR", "DOOR"],
  ["FLOOR", "STAIRS", "WALL"],
];

const STATE: GameStateView = {
  current_floor_index: 0,
  turn_count: 0,
  player: playerAt(1, 1),
  floor: {
    width: 3,
    height: 2,
    tiles: TILES,
    enemies: [],
    items: {},
    stairs_down: [1, 1],
  },
};

describe("drawFloor", () => {
  it("clears the whole backing buffer to the backdrop first", () => {
    const { ctx, fillRectCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      STATE,
      IMAGES,
      PLAYER,
      ENEMIES,
      ITEMS,
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
      ENEMIES,
      ITEMS,
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
      ENEMIES,
      ITEMS,
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
        current_floor_index: 0,
        turn_count: 0,
        player: playerAt(40, 25),
        floor: {
          width: 80,
          height: 50,
          tiles: bigTiles,
          enemies: [],
          items: {},
          stairs_down: [40, 25],
        },
      },
      IMAGES,
      PLAYER,
      ENEMIES,
      ITEMS,
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
      ENEMIES,
      ITEMS,
      0,
    );
    expect(fillRectCalls).toEqual([[0, 0, 240, 160]]);
    expect(drawImageCalls).toEqual([]); // no tiles and, crucially, no player
  });

  it("blits each enemy at its tile, by behaviour, after tiles and before the player", () => {
    // A melee enemy at (0,0) and a boss at (2,1) on the 3×2 floor (camera pinned 0,0).
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      {
        current_floor_index: 0,
        turn_count: 0,
        player: playerAt(1, 1),
        floor: {
          width: 3,
          height: 2,
          tiles: TILES,
          enemies: [
            { position: [0, 0], behaviour: "MELEE" },
            { position: [2, 1], behaviour: "BOSS" },
          ],
          items: {},
          stairs_down: [1, 1],
        },
      },
      IMAGES,
      PLAYER,
      ENEMIES,
      ITEMS,
      0,
    );

    // 6 floor cells, then the two enemies in list order, then the player last.
    const sprites = drawImageCalls.slice(6);
    expect(sprites).toEqual([
      { image: ENEMIES.MELEE, sx: 0, sy: 0, sw: 16, sh: 16 },
      { image: ENEMIES.BOSS, sx: 2 * 16, sy: 1 * 16, sw: 16, sh: 16 },
      { image: PLAYER, sx: 16, sy: 16, sw: 16, sh: 16 },
    ]);
  });

  it("culls enemies outside the viewport", () => {
    // 80×50 floor, player mid-map → camera (33,20), window covers x∈[33,48) y∈[20,30).
    const bigTiles: TileType[][] = Array.from({ length: 50 }, () =>
      Array.from({ length: 80 }, (): TileType => "FLOOR"),
    );
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      {
        current_floor_index: 0,
        turn_count: 0,
        player: playerAt(40, 25),
        floor: {
          width: 80,
          height: 50,
          tiles: bigTiles,
          enemies: [
            { position: [41, 25], behaviour: "RANGED" }, // in view
            { position: [0, 0], behaviour: "MELEE" }, // far off-screen
          ],
          items: {},
          stairs_down: [40, 25],
        },
      },
      IMAGES,
      PLAYER,
      ENEMIES,
      ITEMS,
      0,
    );

    const enemyBlits = drawImageCalls.filter(
      (c) => c.image === ENEMIES.RANGED || c.image === ENEMIES.MELEE,
    );
    // Only the in-view ranged enemy is blitted; the off-screen melee is culled.
    expect(enemyBlits).toEqual([
      { image: ENEMIES.RANGED, sx: 8 * 16, sy: 5 * 16, sw: 16, sh: 16 },
    ]);
  });

  it("blits ground items at their tile, after the floor and before enemies/player", () => {
    // A potion at (0,0) and a weapon at (2,1) on the 3×2 floor (camera pinned 0,0),
    // plus a melee enemy at (2,1) — items paint under the actors.
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      {
        current_floor_index: 0,
        turn_count: 0,
        player: playerAt(1, 1),
        floor: {
          width: 3,
          height: 2,
          tiles: TILES,
          enemies: [{ position: [2, 1], behaviour: "MELEE" }],
          items: {
            "0,0": [{ item_type: "POTION" }],
            "2,1": [{ item_type: "WEAPON" }],
          },
          stairs_down: [1, 1],
        },
      },
      IMAGES,
      PLAYER,
      ENEMIES,
      ITEMS,
      0,
    );

    // 6 floor cells, then the two items, then the enemy, then the player last.
    const sprites = drawImageCalls.slice(6);
    expect(sprites).toEqual([
      { image: ITEMS.POTION, sx: 0, sy: 0, sw: 16, sh: 16 },
      { image: ITEMS.WEAPON, sx: 2 * 16, sy: 1 * 16, sw: 16, sh: 16 },
      { image: ENEMIES.MELEE, sx: 2 * 16, sy: 1 * 16, sw: 16, sh: 16 },
      { image: PLAYER, sx: 16, sy: 16, sw: 16, sh: 16 },
    ]);
  });

  it("draws only the representative (first) item when a tile holds several", () => {
    // One tile, two stacks of different types — only one 16px sprite fits the cell.
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      {
        current_floor_index: 0,
        turn_count: 0,
        player: playerAt(1, 1),
        floor: {
          width: 3,
          height: 2,
          tiles: TILES,
          enemies: [],
          items: { "0,0": [{ item_type: "KEY" }, { item_type: "SHIELD" }] },
          stairs_down: [1, 1],
        },
      },
      IMAGES,
      PLAYER,
      ENEMIES,
      ITEMS,
      0,
    );

    const itemBlits = drawImageCalls.filter((c) =>
      Object.values(ITEMS).includes(c.image as HTMLImageElement),
    );
    expect(itemBlits).toEqual([
      { image: ITEMS.KEY, sx: 0, sy: 0, sw: 16, sh: 16 },
    ]);
  });

  it("culls items outside the viewport", () => {
    // 80×50 floor, player mid-map → camera (33,20), window covers x∈[33,48) y∈[20,30).
    const bigTiles: TileType[][] = Array.from({ length: 50 }, () =>
      Array.from({ length: 80 }, (): TileType => "FLOOR"),
    );
    const { ctx, drawImageCalls } = fakeContext();
    drawFloor(
      ctx as unknown as CanvasRenderingContext2D,
      {
        current_floor_index: 0,
        turn_count: 0,
        player: playerAt(40, 25),
        floor: {
          width: 80,
          height: 50,
          tiles: bigTiles,
          enemies: [],
          items: {
            "41,25": [{ item_type: "POTION" }], // in view
            "0,0": [{ item_type: "WEAPON" }], // far off-screen
          },
          stairs_down: [40, 25],
        },
      },
      IMAGES,
      PLAYER,
      ENEMIES,
      ITEMS,
      0,
    );

    const itemBlits = drawImageCalls.filter((c) =>
      Object.values(ITEMS).includes(c.image as HTMLImageElement),
    );
    // Only the in-view potion is blitted; the off-screen weapon is culled.
    expect(itemBlits).toEqual([
      { image: ITEMS.POTION, sx: 8 * 16, sy: 5 * 16, sw: 16, sh: 16 },
    ]);
  });
});
