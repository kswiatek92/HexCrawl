import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { routes } from "./router";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe("App routing", () => {
  it("renders the game screen at the index route", () => {
    renderAt("/");
    expect(
      screen.getByRole("heading", { name: "HexCrawl" }),
    ).toBeInTheDocument();
  });

  it("renders the nav links on every screen", () => {
    renderAt("/");
    expect(screen.getByRole("link", { name: "Game" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Leaderboard" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Login" })).toBeInTheDocument();
  });

  it("renders the leaderboard screen at /leaderboard", () => {
    // The screen fetches on mount (5.10); keep the request in flight so this
    // routing test never sees a post-assertion (un-acted) state update.
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockReturnValue(new Promise(() => {})),
    );
    try {
      renderAt("/leaderboard");
      expect(
        screen.getByRole("heading", { name: "Leaderboard" }),
      ).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("renders the login screen at /login", () => {
    renderAt("/login");
    expect(screen.getByRole("heading", { name: "Login" })).toBeInTheDocument();
  });
});
