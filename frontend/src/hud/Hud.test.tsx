import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import Hud from "./Hud";
import { INVENTORY_SLOT_COUNT, hpBarColorClass } from "./hudModel";
import { useGameStore } from "../store/gameStore";
import type { GameStateView } from "../types/gameState";

const initialStore = useGameStore.getState();

afterEach(() => {
  // The Hud may still be mounted when this reset runs (RTL's auto-cleanup is
  // registered first, so it runs after this hook) — wrap in act so the
  // store-driven re-render isn't an un-acted update.
  act(() => useGameStore.setState(initialStore, true));
});

const sampleState = (overrides?: {
  hp?: number;
  floorIndex?: number;
  turns?: number;
}): GameStateView => ({
  current_floor_index: overrides?.floorIndex ?? 0,
  turn_count: overrides?.turns ?? 0,
  player: {
    name: "Hero",
    position: [1, 1],
    hp: overrides?.hp ?? 20,
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

describe("hpBarColorClass", () => {
  it("steps healthy → wounded → critical with remaining HP", () => {
    expect(hpBarColorClass(20, 20)).toBe("bg-emerald-500");
    expect(hpBarColorClass(11, 20)).toBe("bg-emerald-500"); // > 50%
    expect(hpBarColorClass(10, 20)).toBe("bg-amber-500"); // 50% is wounded
    expect(hpBarColorClass(6, 20)).toBe("bg-amber-500"); // > 25%
    expect(hpBarColorClass(5, 20)).toBe("bg-red-500"); // 25% is critical
    expect(hpBarColorClass(0, 20)).toBe("bg-red-500");
  });

  it("treats a zero max as critical instead of dividing by zero", () => {
    expect(hpBarColorClass(0, 0)).toBe("bg-red-500");
  });
});

describe("Hud", () => {
  it("renders a dormant placeholder before a run exists", () => {
    render(<Hud />);
    expect(screen.getByTestId("hud")).toHaveTextContent("No active run.");
    expect(screen.queryByTestId("hud-hp")).not.toBeInTheDocument();
  });

  it("shows the player's HP numerically and as a proportional bar", () => {
    useGameStore.getState().startRun(sampleState({ hp: 12 }));
    render(<Hud />);

    expect(screen.getByTestId("hud-hp")).toHaveTextContent("12/20");
    const bar = screen.getByTestId("hud-hp-bar");
    expect(bar.style.width).toBe("60%");
    expect(bar.className).toContain("bg-emerald-500");
  });

  it("renders the floor 1-based from the 0-based engine index", () => {
    useGameStore.getState().startRun(sampleState({ floorIndex: 2 }));
    render(<Hud />);
    expect(screen.getByTestId("hud-floor")).toHaveTextContent("3");
  });

  it("shows the run stats: turns, kills, and combat stats", () => {
    useGameStore.getState().startRun(sampleState({ turns: 42 }));
    useGameStore.getState().applyTurn(sampleState({ turns: 43 }), 5, null);
    render(<Hud />);

    expect(screen.getByTestId("hud-turns")).toHaveTextContent("43");
    expect(screen.getByTestId("hud-kills")).toHaveTextContent("5");
    expect(screen.getByTestId("hud-atk")).toHaveTextContent("3");
    expect(screen.getByTestId("hud-def")).toHaveTextContent("1");
  });

  it("renders the fixed inventory rack, empty in v1", () => {
    useGameStore.getState().startRun(sampleState());
    render(<Hud />);

    const slots = screen.getAllByTestId("hud-inventory-slot");
    expect(slots).toHaveLength(INVENTORY_SLOT_COUNT);
    // No inventory crosses the wire yet, so no slot paints an item icon.
    expect(document.querySelector("img")).toBeNull();
  });

  it("surfaces the last protocol error and hides it once cleared", () => {
    useGameStore.getState().startRun(sampleState());
    useGameStore.getState().setLastError("unknown action 'jump'");
    render(<Hud />);

    expect(screen.getByTestId("hud-error")).toHaveTextContent(
      "unknown action 'jump'",
    );

    // The next successful turn clears the error (store contract) — the HUD
    // must drop the warning, not keep a stale one on screen. The store update
    // re-renders the subscribed component; no rerender() needed.
    act(() => useGameStore.getState().applyTurn(sampleState(), 0, null));
    expect(screen.queryByTestId("hud-error")).not.toBeInTheDocument();
  });
});
