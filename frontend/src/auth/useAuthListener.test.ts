import { renderHook, waitFor } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthListener } from "./useAuthListener";
import { useAuthStore } from "./authStore";
import {
  emitAuthChange,
  fakeAuth,
  makeSession,
  resetAuthStore,
  resetFakeAuth,
} from "../test/fakeSupabase";

vi.mock("./supabaseClient", async () => {
  const { fakeSupabase } = await import("../test/fakeSupabase");
  return { getSupabase: () => fakeSupabase };
});

beforeEach(() => {
  resetFakeAuth();
  resetAuthStore();
});

describe("useAuthListener", () => {
  it("restores a persisted session into the store on mount", async () => {
    const session = makeSession("k@example.com", "restored-token");
    fakeAuth.getSession.mockResolvedValue({ data: { session }, error: null });

    renderHook(() => useAuthListener());

    await waitFor(() =>
      expect(useAuthStore.getState().status).toBe("signed_in"),
    );
    expect(useAuthStore.getState().session?.access_token).toBe(
      "restored-token",
    );
  });

  it("resolves to signed_out when no session is persisted", async () => {
    renderHook(() => useAuthListener());

    await waitFor(() =>
      expect(useAuthStore.getState().status).toBe("signed_out"),
    );
  });

  it("treats a failed restore as signed_out, not a crash", async () => {
    fakeAuth.getSession.mockRejectedValue(new Error("network down"));

    renderHook(() => useAuthListener());

    await waitFor(() =>
      expect(useAuthStore.getState().status).toBe("signed_out"),
    );
  });

  it("follows auth events into the store (login, refresh, logout)", async () => {
    renderHook(() => useAuthListener());
    await waitFor(() =>
      expect(useAuthStore.getState().status).toBe("signed_out"),
    );

    act(() => emitAuthChange(makeSession("k@example.com", "fresh")));
    expect(useAuthStore.getState().session?.access_token).toBe("fresh");

    act(() => emitAuthChange(makeSession("k@example.com", "refreshed")));
    expect(useAuthStore.getState().session?.access_token).toBe("refreshed");

    act(() => emitAuthChange(null));
    expect(useAuthStore.getState().status).toBe("signed_out");
  });

  it("unsubscribes on unmount — later events no longer reach the store", async () => {
    const { unmount } = renderHook(() => useAuthListener());
    await waitFor(() =>
      expect(useAuthStore.getState().status).toBe("signed_out"),
    );

    unmount();
    act(() => emitAuthChange(makeSession()));

    expect(useAuthStore.getState().status).toBe("signed_out");
  });
});
