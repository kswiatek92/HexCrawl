/**
 * Auth session state (tasks 5.11/5.12), following the `gameStore` rules: one
 * normalised Zustand store, one atomic `set()` per action, and an explicit
 * state machine instead of ad-hoc booleans.
 *
 * `status` starts at `"loading"` — the SDK needs an async `getSession()` to
 * restore a persisted session, and without a third state the first paint
 * would flash "signed out" (and the route guard would bounce a logged-in
 * player to /login) before the restore resolves. `useAuthListener` is the
 * only writer; everything else reads via selectors.
 *
 * The store holds the whole `Session` (not just the token): the screens show
 * `user.email`, and the socket/start-game wiring reads `access_token` at the
 * moment of use — after an SDK auto-refresh, `setSession` has already swapped
 * in the new token, so consumers never hold a stale one.
 *
 * Client-side auth state is UX, not security: the backend independently
 * verifies the JWT on every HTTP request (`get_current_user`) and on the WS
 * auth handshake, so lying to this store unlocks nothing (QUIZZES.md 5.12 Q4).
 */

import { create } from "zustand";
import type { Session } from "@supabase/supabase-js";

/** Session restore lifecycle: `loading` until the first getSession resolves. */
export type AuthStatus = "loading" | "signed_out" | "signed_in";

interface AuthState {
  status: AuthStatus;
  /** The Supabase session; non-null exactly when `status` is `"signed_in"`. */
  session: Session | null;
  /**
   * One transition for every auth event: a session (login, restore, token
   * refresh) or its absence (logout, failed restore). Status and session flip
   * in the same `set()` so no render can observe `signed_in` without a token.
   */
  setSession: (session: Session | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  status: "loading",
  session: null,
  setSession: (session) =>
    set({
      session,
      status: session === null ? "signed_out" : "signed_in",
    }),
}));
