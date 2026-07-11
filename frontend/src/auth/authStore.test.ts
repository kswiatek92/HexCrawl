import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "./authStore";
import { makeSession, resetAuthStore } from "../test/fakeSupabase";

beforeEach(resetAuthStore);

describe("authStore", () => {
  it("starts loading — the restore hasn't answered yet", () => {
    expect(useAuthStore.getState().status).toBe("loading");
    expect(useAuthStore.getState().session).toBeNull();
  });

  it("setSession(session) flips to signed_in with the session, atomically", () => {
    const session = makeSession("k@example.com", "tok-1");
    useAuthStore.getState().setSession(session);
    const state = useAuthStore.getState();
    expect(state.status).toBe("signed_in");
    expect(state.session).toBe(session);
  });

  it("setSession(null) flips to signed_out and drops the session", () => {
    useAuthStore.getState().setSession(makeSession());
    useAuthStore.getState().setSession(null);
    const state = useAuthStore.getState();
    expect(state.status).toBe("signed_out");
    expect(state.session).toBeNull();
  });

  it("a refresh replaces the token in place (signed_in → signed_in)", () => {
    useAuthStore.getState().setSession(makeSession("k@example.com", "old"));
    useAuthStore.getState().setSession(makeSession("k@example.com", "new"));
    expect(useAuthStore.getState().session?.access_token).toBe("new");
    expect(useAuthStore.getState().status).toBe("signed_in");
  });
});
