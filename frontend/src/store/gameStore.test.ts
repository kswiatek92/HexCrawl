import { afterEach, describe, expect, it } from "vitest";
import { useGameStore } from "./gameStore";
import type { GameStateView } from "../types/gameState";

const initialState = useGameStore.getState();

afterEach(() => {
  useGameStore.setState(initialState, true);
});

const sampleState = (x: number, y: number): GameStateView => ({
  current_floor_index: 0,
  turn_count: 0,
  player: {
    name: "Hero",
    position: [x, y],
    hp: 20,
    max_hp: 20,
    attack: 3,
    defense: 1,
  },
  floor: {
    width: 1,
    height: 1,
    tiles: [["FLOOR"]],
    enemies: [],
    items: {},
    stairs_down: [0, 0],
  },
});

describe("useGameStore", () => {
  it("starts idle with no run", () => {
    const s = useGameStore.getState();
    expect(s.status).toBe("idle");
    expect(s.gameState).toBeNull();
    expect(s.kills).toBe(0);
    expect(s.lastError).toBeNull();
  });

  it("setStatus updates the connection status", () => {
    useGameStore.getState().setStatus("open");
    expect(useGameStore.getState().status).toBe("open");
  });

  it("startRun seeds the state and zeroes a prior run's stats", () => {
    // Leftovers from a previous run: kills and a lingering error.
    useGameStore.getState().applyTurn(sampleState(1, 1), 4);
    useGameStore.getState().setLastError("unknown action 'jump'");

    const fresh = sampleState(3, 4);
    useGameStore.getState().startRun(fresh);

    const s = useGameStore.getState();
    expect(s.gameState).toEqual(fresh);
    expect(s.kills).toBe(0);
    expect(s.lastError).toBeNull();
  });

  it("applyTurn replaces the state and accumulates kills", () => {
    useGameStore.getState().startRun(sampleState(0, 0));

    const mid = sampleState(1, 0);
    useGameStore.getState().applyTurn(mid, 2);
    expect(useGameStore.getState().gameState).toEqual(mid);
    expect(useGameStore.getState().kills).toBe(2);

    const late = sampleState(2, 0);
    useGameStore.getState().applyTurn(late, 1);
    expect(useGameStore.getState().gameState).toEqual(late);
    expect(useGameStore.getState().kills).toBe(3);
  });

  it("applyTurn clears the last error — the loop recovered", () => {
    useGameStore.getState().setLastError("frame must be a JSON object");
    expect(useGameStore.getState().lastError).toBe(
      "frame must be a JSON object",
    );

    useGameStore.getState().applyTurn(sampleState(1, 1), 0);
    expect(useGameStore.getState().lastError).toBeNull();
  });

  it("resetRun blanks the run state, kills, and error", () => {
    useGameStore.getState().applyTurn(sampleState(1, 1), 5);
    useGameStore.getState().setLastError("boom");

    useGameStore.getState().resetRun();

    const s = useGameStore.getState();
    expect(s.gameState).toBeNull();
    expect(s.kills).toBe(0);
    expect(s.lastError).toBeNull();
  });
});
