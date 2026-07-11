/**
 * `useAuthListener` — owns the Supabase auth subscription lifecycle (5.12).
 *
 * Same division of labour as `useGameSocket`: the hook owns the long-lived
 * side-effecting object (here the `onAuthStateChange` subscription) inside an
 * effect with a cleanup, and the store holds the state everyone reads.
 * Mounted once in `App` so the session is live on every route.
 *
 * Two sources feed the store:
 *  - `getSession()` on mount — restores a persisted session (localStorage)
 *    and resolves the store's initial `"loading"` to a real answer.
 *  - `onAuthStateChange` — every subsequent transition: SIGNED_IN,
 *    SIGNED_OUT, and crucially TOKEN_REFRESHED, which is how the SDK's
 *    auto-refresh lands a fresh `access_token` in the store without any
 *    bespoke expiry code (QUIZZES.md 5.12 Q2).
 *
 * The `active` flag mirrors the socket hook's: cleanup flips it so a
 * `getSession()` resolving after unmount (StrictMode's mount→unmount→mount,
 * or a real teardown) can't write the store for a dead subscription. The
 * listener itself is torn down via `subscription.unsubscribe()`.
 */

import { useEffect } from "react";
import { useAuthStore } from "./authStore";
import { getSupabase } from "./supabaseClient";

export function useAuthListener(): void {
  const setSession = useAuthStore((s) => s.setSession);

  useEffect(() => {
    let active = true;
    const supabase = getSupabase();

    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (active) setSession(data.session);
      })
      .catch(() => {
        // A failed restore (network, corrupt storage) is "not signed in",
        // not a crash — the user can still reach the login screen.
        if (active) setSession(null);
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) setSession(session);
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [setSession]);
}
