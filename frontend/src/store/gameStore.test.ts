import { afterEach, describe, expect, it } from "vitest";
import { useGameStore } from "./gameStore";

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
});
