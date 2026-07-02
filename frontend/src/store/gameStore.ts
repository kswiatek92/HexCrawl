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
 *
 * Task 5.9 adds the **run lifecycle as an explicit state machine** (QUIZZES
 * 5.9 Q2): `phase` names the run's state (`idle → playing → game_over`)
 * instead of scattering booleans (`isDead`, `isPlaying`, …) that can drift
 * into impossible combinations. It is deliberately a *separate* machine from
 * `status`: a dropped connection mid-run is `closed`+`playing` (not a game
 * over), while a finished run is `closed`+`game_over` — collapsing the two
 * would make that distinction inexpressible. Only the run actions below move
 * the phase; game over lands in `applyTurn`'s single `set()` so the final
 * state, kills, and phase flip together.
 */
export type ConnectionStatus = "idle" | "connecting" | "open" | "closed";

/** The run-lifecycle states. `game_over` keeps the final state readable. */
export type RunPhase = "idle" | "playing" | "game_over";

/**
 * How a run ended — derived by the socket hook from the final frame's events
 * (`player_died` → died, `run_abandoned` → abandoned), never guessed here.
 */
export type GameOverCause = "died" | "abandoned";

interface GameState {
  status: ConnectionStatus;
  /** Where the run is in its lifecycle. Moved only by the run actions below. */
  phase: RunPhase;
  /** Why the run ended; `null` unless `phase` is `"game_over"`. */
  gameOverCause: GameOverCause | null;
  /** Latest state pushed over the socket, or `null` before a run is connected. */
  gameState: GameStateView | null;
  /** Enemies killed this run, aggregated client-side from `enemy_killed` events. */
  kills: number;
  /** Detail of the last `error` frame, cleared by the next successful turn. */
  lastError: string | null;
  setStatus: (status: ConnectionStatus) => void;
  /** A `connected` frame: seed the run's state, zero the per-run stats. */
  startRun: (gameState: GameStateView) => void;
  /**
   * A `turn` frame: new state + this turn's kills, and the loop recovered.
   * A non-null `gameOver` is the run's final frame — the phase flips to
   * `game_over` in the same `set()`, keeping the transition atomic.
   */
  applyTurn: (
    gameState: GameStateView,
    killsDelta: number,
    gameOver: GameOverCause | null,
  ) => void;
  /** A recoverable `error` frame — surfaced by the HUD (task 5.8). */
  setLastError: (detail: string) => void;
  /** Blank the run (reconnect/teardown/new-run) so no stale run state can paint. */
  resetRun: () => void;
}

export const useGameStore = create<GameState>((set) => ({
  status: "idle",
  phase: "idle",
  gameOverCause: null,
  gameState: null,
  kills: 0,
  lastError: null,
  setStatus: (status) => set({ status }),
  startRun: (gameState) =>
    set({
      gameState,
      phase: "playing",
      gameOverCause: null,
      kills: 0,
      lastError: null,
    }),
  applyTurn: (gameState, killsDelta, gameOver) =>
    set((s) => ({
      gameState,
      kills: s.kills + killsDelta,
      lastError: null,
      // "A turn happened" implies a live run: `idle` self-normalises to
      // `playing` (so `idle`+state is unrepresentable even if a turn beats
      // `startRun`), and `game_over` is sticky — only startRun/resetRun leave it.
      phase:
        gameOver !== null || s.phase === "game_over" ? "game_over" : "playing",
      gameOverCause: gameOver !== null ? gameOver : s.gameOverCause,
    })),
  setLastError: (detail) => set({ lastError: detail }),
  resetRun: () =>
    set({
      gameState: null,
      phase: "idle",
      gameOverCause: null,
      kills: 0,
      lastError: null,
    }),
}));
