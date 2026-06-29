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

/** The three `BehaviourType` enum values, as their wire strings (StrEnum). */
export type BehaviourType = "MELEE" | "RANGED" | "BOSS";

/** The five `ItemType` enum values, as their wire strings (StrEnum). */
export type ItemType = "WEAPON" | "ARMOR" | "SHIELD" | "POTION" | "KEY";

/** A position on the floor grid, `[x, y]`. */
export type Position = readonly [number, number];

export interface PlayerView {
  position: Position;
}

/**
 * An enemy on the current floor — the subset the renderer paints. `behaviour`
 * selects the sprite (task 5.5); HP / stats arrive when the HUD lands (5.8).
 */
export interface EnemyView {
  position: Position;
  behaviour: BehaviourType;
}

/**
 * A ground-item stack on the current floor — the subset the renderer paints.
 * `item_type` selects the sprite (task 5.5a); its tile comes from the
 * `FloorView.items` key, so no position field is needed here. Name / effect /
 * count arrive when the HUD inventory lands (5.8).
 */
export interface ItemView {
  item_type: ItemType;
}

export interface FloorView {
  width: number;
  height: number;
  /** Row-major grid: `tiles[y][x]`. */
  tiles: TileType[][];
  /** Enemies on this floor (mirrors backend `FloorState.enemies`). */
  enemies: EnemyView[];
  /**
   * Ground-item stacks keyed by `"x,y"` tile string — mirrors backend
   * `FloorState.items` (`dict[str, list[ItemState]]`). JSON object keys are
   * strings, hence the stringified position.
   */
  items: Record<string, ItemView[]>;
  stairs_down: Position;
}

export interface GameStateView {
  player: PlayerView;
  floor: FloorView;
}
