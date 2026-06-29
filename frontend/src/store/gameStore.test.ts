import { afterEach, describe, expect, it } from "vitest";
import { useGameStore } from "./gameStore";
import type { GameStateView } from "../types/gameState";

const initialState = useGameStore.getState();

afterEach(() => {
  useGameStore.setState(initialState, true);
});

describe("useGameStore", () => {
  it("starts idle", () => {
    expect(useGameStore.getState().status).toBe("idle");
  });

  it("setStatus updates the connection status", () => {
    useGameStore.getState().setStatus("open");
    expect(useGameStore.getState().status).toBe("open");
  });

  it("starts with no game state", () => {
    expect(useGameStore.getState().gameState).toBeNull();
  });

  it("setGameState stores and clears the latest state", () => {
    const state: GameStateView = {
      player: { position: [3, 4] },
      floor: {
        width: 1,
        height: 1,
        tiles: [["FLOOR"]],
        enemies: [],
        items: {},
        stairs_down: [0, 0],
      },
    };
    useGameStore.getState().setGameState(state);
    expect(useGameStore.getState().gameState).toEqual(state);

    useGameStore.getState().setGameState(null);
    expect(useGameStore.getState().gameState).toBeNull();
  });
});
