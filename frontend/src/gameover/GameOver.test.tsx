import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import GameOver from "./GameOver";
import { useGameStore, type GameOverCause } from "../store/gameStore";
import type { GameStateView } from "../types/gameState";

const initialStore = useGameStore.getState();

afterEach(() => {
  // The overlay may still be mounted when this reset runs (RTL's auto-cleanup
  // is registered first, so it runs after this hook) — wrap in act so the
  // store-driven re-render isn't an un-acted update.
  act(() => useGameStore.setState(initialStore, true));
});

const sampleState = (overrides?: {
  floorIndex?: number;
  turns?: number;
}): GameStateView => ({
  current_floor_index: overrides?.floorIndex ?? 0,
  turn_count: overrides?.turns ?? 0,
  player: {
    name: "Hero",
    position: [1, 1],
    hp: 0,
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

/** Drive the store through a full run into game over, like the socket would. */
const endRun = (
  cause: GameOverCause,
  overrides?: { floorIndex?: number; turns?: number; kills?: number },
) => {
  useGameStore.getState().startRun(sampleState());
  useGameStore
    .getState()
    .applyTurn(sampleState(overrides), overrides?.kills ?? 0, cause);
};

/** The overlay renders a router `<Link>`, so tests mount it inside one. */
const renderGameOver = () =>
  render(
    <MemoryRouter>
      <GameOver />
    </MemoryRouter>,
  );

describe("GameOver", () => {
  it("renders nothing before a run exists", () => {
    renderGameOver();
    expect(screen.queryByTestId("gameover")).not.toBeInTheDocument();
  });

  it("renders nothing while the run is still playing", () => {
    useGameStore.getState().startRun(sampleState());
    useGameStore.getState().applyTurn(sampleState(), 2, null);
    renderGameOver();
    expect(screen.queryByTestId("gameover")).not.toBeInTheDocument();
  });

  it("announces itself as a modal dialog named by the headline", () => {
    endRun("died");
    renderGameOver();

    const dialog = screen.getByRole("dialog", { name: "GAME OVER" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("headlines a death as GAME OVER", () => {
    endRun("died");
    renderGameOver();
    expect(screen.getByTestId("gameover-title")).toHaveTextContent("GAME OVER");
  });

  it("headlines an abandoned run as RUN ABANDONED", () => {
    endRun("abandoned");
    renderGameOver();
    expect(screen.getByTestId("gameover-title")).toHaveTextContent(
      "RUN ABANDONED",
    );
  });

  it("shows the final score inputs, floor rendered 1-based", () => {
    endRun("died", { floorIndex: 4, turns: 87, kills: 12 });
    renderGameOver();

    expect(screen.getByTestId("gameover-floor")).toHaveTextContent("5");
    expect(screen.getByTestId("gameover-kills")).toHaveTextContent("12");
    expect(screen.getByTestId("gameover-turns")).toHaveTextContent("87");
  });

  it("points a death at the leaderboard, where the score lands", () => {
    endRun("died");
    renderGameOver();

    const link = screen.getByRole("link", { name: /leaderboard/i });
    expect(link).toHaveAttribute("href", "/leaderboard");
  });

  it("offers no leaderboard link for an abandoned run — it scores nothing", () => {
    endRun("abandoned");
    renderGameOver();
    expect(
      screen.queryByRole("link", { name: /leaderboard/i }),
    ).not.toBeInTheDocument();
  });

  it("New Run resets the store to idle and unmounts the overlay", () => {
    endRun("died");
    renderGameOver();

    act(() => screen.getByRole("button", { name: "New Run" }).click());

    expect(useGameStore.getState().phase).toBe("idle");
    expect(useGameStore.getState().gameState).toBeNull();
    expect(screen.queryByTestId("gameover")).not.toBeInTheDocument();
  });
});
