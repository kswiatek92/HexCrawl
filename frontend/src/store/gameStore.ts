import { create } from "zustand";

/**
 * Connection lifecycle for the WebSocket turn loop.
 *
 * The real socket wiring lands in task 5.6 (`useGameSocket`); this store is the
 * minimal, typed seam that hook will drive. Kept deliberately small for 5.1 —
 * just enough to prove Zustand is wired and exercise it under test.
 */
export type ConnectionStatus = "idle" | "connecting" | "open" | "closed";

interface GameState {
  status: ConnectionStatus;
  setStatus: (status: ConnectionStatus) => void;
}

export const useGameStore = create<GameState>((set) => ({
  status: "idle",
  setStatus: (status) => set({ status }),
}));
