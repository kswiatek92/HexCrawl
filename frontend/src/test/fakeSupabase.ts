/**
 * Shared Supabase test double (tasks 5.11/5.12).
 *
 * A hand-written fake of the *SDK surface the app actually uses* — the same
 * philosophy as the backend's fake ports: mock our seam (`getSupabase()`),
 * never the network. Test files stub the client module with an async factory
 * (dynamic import dodges `vi.mock` hoisting):
 *
 *   vi.mock("../auth/supabaseClient", async () => {
 *     const { fakeSupabase } = await import("../test/fakeSupabase");
 *     return { getSupabase: () => fakeSupabase };
 *   });
 *
 * and call `resetFakeAuth()` in `beforeEach` — the fake is a module-level
 * singleton (so the mocked module and the test observe the same object), which
 * means its call history and programmed behaviour would otherwise leak
 * between tests. Defaults model a signed-out project: no persisted session,
 * auth calls succeed.
 */

import { vi } from "vitest";
import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { useAuthStore } from "../auth/authStore";

/** A minimal but token-carrying session; enough for everything the app reads. */
export function makeSession(
  email = "player@example.com",
  accessToken = "test-access-token",
): Session {
  return {
    access_token: accessToken,
    refresh_token: "test-refresh-token",
    expires_in: 3600,
    token_type: "bearer",
    user: { id: "user-1", email },
  } as unknown as Session;
}

type AuthChangeCallback = (event: string, session: Session | null) => void;

export const fakeAuth = {
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  signOut: vi.fn(),
};

/** Callbacks registered via `onAuthStateChange`; fire to simulate SDK events. */
export function emitAuthChange(session: Session | null): void {
  for (const callback of registeredCallbacks) {
    callback("TEST_EVENT", session);
  }
}

let registeredCallbacks: AuthChangeCallback[] = [];

/** Fresh defaults + empty call history. Call in `beforeEach`. */
export function resetFakeAuth(): void {
  registeredCallbacks = [];
  fakeAuth.getSession
    .mockReset()
    .mockResolvedValue({ data: { session: null }, error: null });
  fakeAuth.onAuthStateChange
    .mockReset()
    .mockImplementation((callback: AuthChangeCallback) => {
      registeredCallbacks.push(callback);
      return {
        data: {
          subscription: {
            unsubscribe: vi.fn(() => {
              registeredCallbacks = registeredCallbacks.filter(
                (c) => c !== callback,
              );
            }),
          },
        },
      };
    });
  fakeAuth.signInWithPassword
    .mockReset()
    .mockResolvedValue({ data: {}, error: null });
  fakeAuth.signUp
    .mockReset()
    .mockResolvedValue({ data: { user: null, session: null }, error: null });
  fakeAuth.signOut.mockReset().mockResolvedValue({ error: null });
}

resetFakeAuth();

export const fakeSupabase = { auth: fakeAuth } as unknown as SupabaseClient;

/** Zustand stores are module singletons — blank auth state between tests. */
export function resetAuthStore(): void {
  useAuthStore.setState({ status: "loading", session: null });
}
