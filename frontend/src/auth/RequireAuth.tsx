/**
 * Route guard (task 5.11): gates children on a signed-in session.
 *
 * Three-way, never two-way: `loading` renders a placeholder instead of
 * redirecting, because bouncing a logged-in player to /login while the
 * persisted session is still restoring would be a wrong answer given too
 * early — the store's third state exists exactly for this.
 *
 * This guard is UX only (QUIZZES.md 5.11 Q5). It decides what to *render*;
 * it proves nothing. The server independently verifies the JWT on every
 * guarded resource — `get_current_user` on `POST /game/start`, the
 * first-message auth handshake on the WS — so bypassing this component
 * (devtools, a hand-rolled fetch) still hits 401/1008 at the boundary.
 */

import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "./authStore";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status);

  if (status === "loading") {
    return (
      <p data-testid="auth-guard-loading" className="text-slate-400">
        Checking session…
      </p>
    );
  }
  if (status === "signed_out") {
    return <Navigate to="/login" replace />;
  }
  return children;
}
