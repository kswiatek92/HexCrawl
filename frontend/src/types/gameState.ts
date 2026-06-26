/**
 * TypeScript mirror of the backend game-state wire shape — the subset the canvas
 * renderer needs.
 *
 * Source of truth is the Pydantic contract in
 * `src/entrypoints/http/schemas.py` (`GameStateResponse` / `FloorState` /
 * `PlayerState`). This file is deliberately a *subset*: 5.3 only draws the floor
 * grid, so enemies / items / stats are typed loosely or omitted and will be
 * tightened when the consuming tasks (5.4/5.5/5.8) land. The full state arrives
 * over the WebSocket in task 5.6; this is the read model the renderer paints.
 *
 * Coordinate conventions (must match the backend):
 *  - `tiles` is row-major: `tiles[y][x]`.
 *  - positions cross the wire as `[x, y]` tuples.
 */

/** The four `TileType` enum values, as their wire strings (StrEnum). */
export type TileType = "WALL" | "FLOOR" | "STAIRS" | "DOOR";

/** A position on the floor grid, `[x, y]`. */
export type Position = readonly [number, number];

export interface PlayerView {
  position: Position;
}

export interface FloorView {
  width: number;
  height: number;
  /** Row-major grid: `tiles[y][x]`. */
  tiles: TileType[][];
  stairs_down: Position;
}

export interface GameStateView {
  player: PlayerView;
  floor: FloorView;
}
