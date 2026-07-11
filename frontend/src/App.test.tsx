import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "./router";
import {
  fakeAuth,
  makeSession,
  resetAuthStore,
  resetFakeAuth,
} from "./test/fakeSupabase";

vi.mock("./auth/supabaseClient", async () => {
  const { fakeSupabase } = await import("./test/fakeSupabase");
  return { getSupabase: () => fakeSupabase };
});

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  resetFakeAuth();
  resetAuthStore();
});

describe("App routing", () => {
  it("redirects the index route to login while signed out (5.11 guard)", async () => {
    renderAt("/");
    // getSession resolves to no session → the guard bounces to /login.
    expect(
      await screen.findByRole("heading", { name: "Account" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "HexCrawl" })).toBeNull();
  });

  it("renders the game screen at the index route when signed in", async () => {
    fakeAuth.getSession.mockResolvedValue({
      data: { session: makeSession() },
      error: null,
    });
    renderAt("/");
    expect(
      await screen.findByRole("heading", { name: "HexCrawl" }),
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

  it("renders the auth screen at /login", async () => {
    renderAt("/login");
    expect(
      screen.getByRole("heading", { name: "Account" }),
    ).toBeInTheDocument();
    // Session restore resolves signed-out → the login/register form shows.
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });
});
