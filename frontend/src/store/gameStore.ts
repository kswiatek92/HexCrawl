import { create } from "zustand";
import type { GameStateView } from "../types/gameState";

/**
 * Connection lifecycle + latest game state for the WebSocket turn loop.
 *
 * The seam was shipped in 5.1; task 5.6 (`useGameSocket`) drives it: the hook
 * writes `status` as the socket opens/closes and `gameState` as each
 * `connected` / `turn` frame arrives, and any component (e.g. `GameScreen` →
 * `GameCanvas`) reads them via a selector — so the renderer is decoupled from
 * wherever the socket is mounted.
 */
export type ConnectionStatus = "idle" | "connecting" | "open" | "closed";

interface GameState {
  status: ConnectionStatus;
  /** Latest state pushed over the socket, or `null` before a run is connected. */
  gameState: GameStateView | null;
  setStatus: (status: ConnectionStatus) => void;
  setGameState: (gameState: GameStateView | null) => void;
}

export const useGameStore = create<GameState>((set) => ({
  status: "idle",
  gameState: null,
  setStatus: (status) => set({ status }),
  setGameState: (gameState) => set({ gameState }),
}));
