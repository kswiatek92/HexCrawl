import { createBrowserRouter, type RouteObject } from "react-router-dom";
import App from "./App";
import RequireAuth from "./auth/RequireAuth";
import GameScreen from "./routes/GameScreen";
import LeaderboardScreen from "./routes/LeaderboardScreen";
import LoginScreen from "./routes/LoginScreen";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <App />,
    children: [
      // The game needs a session (start-game + the WS handshake are authed);
      // the guard is UX only — the server re-verifies the JWT regardless.
      {
        index: true,
        element: (
          <RequireAuth>
            <GameScreen />
          </RequireAuth>
        ),
      },
      // Public: the boards are unauthenticated reads (tasks 3.10/3.11).
      { path: "leaderboard", element: <LeaderboardScreen /> },
      { path: "login", element: <LoginScreen /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
