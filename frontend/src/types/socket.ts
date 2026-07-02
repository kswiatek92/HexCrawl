/**
 * TypeScript mirror of the WebSocket turn-loop wire protocol.
 *
 * Source of truth is the backend at `src/entrypoints/ws/protocol.py` (frame
 * shapes) and `src/entrypoints/ws/router_game.py` (the lifecycle: first-message
 * auth, then `connected` / `turn` / `error` frames). This file is the client
 * half of that contract — the `useGameSocket` hook (task 5.6) hardcodes these
 * shapes. Keep it in lockstep with the Python side: an action name, a frame
 * `type`, or a `Direction` value that drifts here is a silent protocol break.
 *
 * Positions cross the wire as `[x, y]` arrays; that read-model lives in
 * `gameState.ts` (`GameStateView`), which both inbound state frames carry.
 */

import type { GameStateView } from "./gameState";

/** The four `Direction` enum values (StrEnum), as their wire strings. */
export type Direction = "NORTH" | "SOUTH" | "EAST" | "WEST";

/**
 * An action the client sends to drive one turn — the inbound shape
 * `parse_action` expects. `move`/`attack`/`open` carry a `direction`; `use_item`
 * carries an `item_id` (UUID string); the rest are bare. Modelled as a
 * discriminated union on `action` so a missing/extra field is a type error.
 */
export type ClientAction =
  | { action: "move" | "attack" | "open"; direction: Direction }
  | { action: "use_item"; item_id: string }
  | { action: "wait" | "descend" | "abandon" | "pickup" };

/**
 * The auth handshake frame — the very first thing the client sends after the
 * socket opens, before any action. Mirrors the `{"type": "auth", "token": ...}`
 * frame `_authenticate` awaits server-side.
 */
export interface AuthFrame {
  type: "auth";
  token: string;
}

/** Initial state pushed once the run is authorised at connect. */
export interface ConnectedFrame {
  type: "connected";
  game_id: string;
  state: GameStateView;
}

/**
 * One serialised `TurnEvent` — `serialize_event` always emits a snake_case
 * `type` discriminator (e.g. `"enemy_killed"`) plus variant-specific fields.
 * Only the discriminator is typed: the HUD's kills counter (task 5.8) switches
 * on it, and the per-variant payloads stay loose until something reads them.
 */
export type TurnEventFrame = { type: string } & Record<string, unknown>;

/**
 * The result of one turn: the event narrative, the new state, and whether the
 * run ended.
 */
export interface TurnFrame {
  type: "turn";
  events: ReadonlyArray<TurnEventFrame>;
  state: GameStateView;
  game_over: boolean;
}

/** A recoverable bad-message reply; the server keeps the loop alive. */
export interface ErrorFrame {
  type: "error";
  detail: string;
}

/** Any frame the server can push down the socket. */
export type ServerFrame = ConnectedFrame | TurnFrame | ErrorFrame;
