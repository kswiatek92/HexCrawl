import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
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
    renderAt("/leaderboard");
    expect(
      screen.getByRole("heading", { name: "Leaderboard" }),
    ).toBeInTheDocument();
  });

  it("renders the login screen at /login", () => {
    renderAt("/login");
    expect(screen.getByRole("heading", { name: "Login" })).toBeInTheDocument();
  });
});
