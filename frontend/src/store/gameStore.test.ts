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
    expect(s.phase).toBe("idle");
    expect(s.gameOverCause).toBeNull();
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
    useGameStore.getState().applyTurn(sampleState(1, 1), 4, null);
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
    useGameStore.getState().applyTurn(mid, 2, null);
    expect(useGameStore.getState().gameState).toEqual(mid);
    expect(useGameStore.getState().kills).toBe(2);

    const late = sampleState(2, 0);
    useGameStore.getState().applyTurn(late, 1, null);
    expect(useGameStore.getState().gameState).toEqual(late);
    expect(useGameStore.getState().kills).toBe(3);
  });

  it("applyTurn clears the last error — the loop recovered", () => {
    useGameStore.getState().setLastError("frame must be a JSON object");
    expect(useGameStore.getState().lastError).toBe(
      "frame must be a JSON object",
    );

    useGameStore.getState().applyTurn(sampleState(1, 1), 0, null);
    expect(useGameStore.getState().lastError).toBeNull();
  });

  it("resetRun blanks the run state, kills, and error", () => {
    useGameStore.getState().applyTurn(sampleState(1, 1), 5, null);
    useGameStore.getState().setLastError("boom");

    useGameStore.getState().resetRun();

    const s = useGameStore.getState();
    expect(s.gameState).toBeNull();
    expect(s.kills).toBe(0);
    expect(s.lastError).toBeNull();
  });

  describe("run-lifecycle state machine (5.9)", () => {
    it("startRun enters playing with no cause", () => {
      useGameStore.getState().startRun(sampleState(0, 0));

      expect(useGameStore.getState().phase).toBe("playing");
      expect(useGameStore.getState().gameOverCause).toBeNull();
    });

    it("a turn that beats startRun still self-normalises to playing", () => {
      // Defensive: `idle` + a live gameState must be unrepresentable even if
      // a turn frame arrives before the connected frame seeded the run.
      useGameStore.getState().applyTurn(sampleState(1, 0), 0, null);

      expect(useGameStore.getState().phase).toBe("playing");
    });

    it("game_over is sticky against a stray late turn", () => {
      useGameStore.getState().startRun(sampleState(0, 0));
      useGameStore.getState().applyTurn(sampleState(1, 1), 0, "died");

      // The socket can't deliver this (server closes after game over), but
      // the machine must not fall back to playing if something ever does.
      useGameStore.getState().applyTurn(sampleState(1, 1), 0, null);

      expect(useGameStore.getState().phase).toBe("game_over");
      expect(useGameStore.getState().gameOverCause).toBe("died");
    });

    it("an ordinary turn stays in playing", () => {
      useGameStore.getState().startRun(sampleState(0, 0));
      useGameStore.getState().applyTurn(sampleState(1, 0), 1, null);

      expect(useGameStore.getState().phase).toBe("playing");
      expect(useGameStore.getState().gameOverCause).toBeNull();
    });

    it("a final turn flips to game_over with the cause, atomically", () => {
      useGameStore.getState().startRun(sampleState(0, 0));

      const final = sampleState(2, 2);
      useGameStore.getState().applyTurn(final, 1, "died");

      // One set(): the phase, cause, final state, and kills land together.
      const s = useGameStore.getState();
      expect(s.phase).toBe("game_over");
      expect(s.gameOverCause).toBe("died");
      expect(s.gameState).toEqual(final);
      expect(s.kills).toBe(1);
    });

    it("records an abandoned run's cause", () => {
      useGameStore.getState().startRun(sampleState(0, 0));
      useGameStore.getState().applyTurn(sampleState(0, 0), 0, "abandoned");

      expect(useGameStore.getState().phase).toBe("game_over");
      expect(useGameStore.getState().gameOverCause).toBe("abandoned");
    });

    it("keeps the final stats readable after game over (no reset)", () => {
      useGameStore.getState().startRun(sampleState(0, 0));
      useGameStore.getState().applyTurn(sampleState(1, 0), 3, null);
      useGameStore.getState().applyTurn(sampleState(1, 1), 1, "died");

      // The game-over screen reads these; only resetRun/startRun may blank them.
      expect(useGameStore.getState().gameState).not.toBeNull();
      expect(useGameStore.getState().kills).toBe(4);
    });

    it("resetRun returns to idle and clears the cause", () => {
      useGameStore.getState().startRun(sampleState(0, 0));
      useGameStore.getState().applyTurn(sampleState(1, 1), 0, "died");

      useGameStore.getState().resetRun();

      expect(useGameStore.getState().phase).toBe("idle");
      expect(useGameStore.getState().gameOverCause).toBeNull();
    });

    it("startRun after a game over clears the previous run's cause", () => {
      useGameStore.getState().startRun(sampleState(0, 0));
      useGameStore.getState().applyTurn(sampleState(1, 1), 0, "abandoned");

      useGameStore.getState().startRun(sampleState(0, 0));

      expect(useGameStore.getState().phase).toBe("playing");
      expect(useGameStore.getState().gameOverCause).toBeNull();
    });
  });
});
