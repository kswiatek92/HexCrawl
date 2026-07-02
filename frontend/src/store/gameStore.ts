import { create } from "zustand";
import type { GameStateView } from "../types/gameState";

/**
 * Connection lifecycle + latest game state for the WebSocket turn loop.
 *
 * The seam was shipped in 5.1; task 5.6 (`useGameSocket`) drives it: the hook
 * writes `status` as the socket opens/closes and dispatches one action per
 * inbound frame, and any component (`GameScreen` → `GameCanvas`, the HUD) reads
 * via a selector — so the renderers are decoupled from wherever the socket is
 * mounted.
 *
 * Task 5.8 grows the store into the HUD's read model. Two rules shape it:
 *
 *  - **One action per frame, one `set()` per action** (QUIZZES 5.8 Q1): a
 *    `turn` frame updates `gameState` *and* `kills` *and* clears `lastError`
 *    atomically, so no render can observe a half-applied frame — the reason
 *    this is one normalised store and not scattered `useState` calls.
 *  - **Run-scoped derived stats live here, not on the wire.** The backend keeps
 *    no kill counter — `enemy_killed` events are the source of truth (see
 *    `ScoreService.compute`'s caller-supplied `kills`) — so the client
 *    aggregates them into `kills`. `startRun`/`resetRun` zero it so a stat
 *    never leaks across runs.
 */
export type ConnectionStatus = "idle" | "connecting" | "open" | "closed";

interface GameState {
  status: ConnectionStatus;
  /** Latest state pushed over the socket, or `null` before a run is connected. */
  gameState: GameStateView | null;
  /** Enemies killed this run, aggregated client-side from `enemy_killed` events. */
  kills: number;
  /** Detail of the last `error` frame, cleared by the next successful turn. */
  lastError: string | null;
  setStatus: (status: ConnectionStatus) => void;
  /** A `connected` frame: seed the run's state, zero the per-run stats. */
  startRun: (gameState: GameStateView) => void;
  /** A `turn` frame: new state + this turn's kills, and the loop recovered. */
  applyTurn: (gameState: GameStateView, killsDelta: number) => void;
  /** A recoverable `error` frame — surfaced by the HUD (task 5.8). */
  setLastError: (detail: string) => void;
  /** Blank the run (reconnect/teardown) so no stale run state can paint. */
  resetRun: () => void;
}

export const useGameStore = create<GameState>((set) => ({
  status: "idle",
  gameState: null,
  kills: 0,
  lastError: null,
  setStatus: (status) => set({ status }),
  startRun: (gameState) => set({ gameState, kills: 0, lastError: null }),
  applyTurn: (gameState, killsDelta) =>
    set((s) => ({ gameState, kills: s.kills + killsDelta, lastError: null })),
  setLastError: (detail) => set({ lastError: detail }),
  resetRun: () => set({ gameState: null, kills: 0, lastError: null }),
}));
