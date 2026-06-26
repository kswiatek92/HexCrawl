import { createBrowserRouter, type RouteObject } from "react-router-dom";
import App from "./App";
import GameScreen from "./routes/GameScreen";
import LeaderboardScreen from "./routes/LeaderboardScreen";
import LoginScreen from "./routes/LoginScreen";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <GameScreen /> },
      { path: "leaderboard", element: <LeaderboardScreen /> },
      { path: "login", element: <LoginScreen /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
