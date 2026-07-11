import { render, screen } from "@testing-library/react";
import {
  createMemoryRouter,
  RouterProvider,
  type RouteObject,
} from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import RequireAuth from "./RequireAuth";
import { useAuthStore } from "./authStore";
import { makeSession, resetAuthStore } from "../test/fakeSupabase";

/**
 * A minimal two-route tree instead of the app's `routes`: the guard's
 * contract (render / hold / redirect) is what's under test, not the app's
 * screens — App.test.tsx covers the real wiring.
 */
const routes: RouteObject[] = [
  {
    path: "/",
    element: (
      <RequireAuth>
        <p data-testid="guarded">secret world</p>
      </RequireAuth>
    ),
  },
  { path: "/login", element: <p data-testid="login-page">login here</p> },
];

function renderGuarded() {
  const router = createMemoryRouter(routes, { initialEntries: ["/"] });
  return render(<RouterProvider router={router} />);
}

beforeEach(resetAuthStore);

describe("RequireAuth", () => {
  it("holds on a placeholder while the session is restoring", () => {
    renderGuarded(); // store starts at "loading"
    expect(screen.getByTestId("auth-guard-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("guarded")).toBeNull();
    expect(screen.queryByTestId("login-page")).toBeNull(); // crucially: no bounce
  });

  it("redirects to /login once signed out", () => {
    useAuthStore.getState().setSession(null);
    renderGuarded();
    expect(screen.getByTestId("login-page")).toBeInTheDocument();
    expect(screen.queryByTestId("guarded")).toBeNull();
  });

  it("renders the children when signed in", () => {
    useAuthStore.getState().setSession(makeSession());
    renderGuarded();
    expect(screen.getByTestId("guarded")).toBeInTheDocument();
  });
});
