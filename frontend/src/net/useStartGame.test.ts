import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { playerNameFromEmail, useStartGame } from "./useStartGame";

describe("playerNameFromEmail", () => {
  it("takes the email's local part", () => {
    expect(playerNameFromEmail("krzysztof@example.com")).toBe("krzysztof");
  });

  it("falls back when there is nothing usable", () => {
    expect(playerNameFromEmail(undefined)).toBe("player");
    expect(playerNameFromEmail("")).toBe("player");
    expect(playerNameFromEmail("@example.com")).toBe("player");
  });

  it("clamps to the backend's 32-char bound", () => {
    const long = "x".repeat(40);
    expect(playerNameFromEmail(`${long}@example.com`)).toHaveLength(32);
  });
});

/** A minimal 201 reply carrying the only field the hook reads. */
function startedResponse(gameId: string): Response {
  return new Response(JSON.stringify({ game_id: gameId }), { status: 201 });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useStartGame", () => {
  it("POSTs /api/v1/game/start with the bearer token and stores game_id", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(startedResponse("run-42"));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useStartGame());
    await act(() => result.current.start("jwt-token", "krzysztof"));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/game/start",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer jwt-token",
        }),
        body: JSON.stringify({ player_name: "krzysztof" }),
      }),
    );
    expect(result.current.request).toEqual({
      status: "started",
      gameId: "run-42",
    });
  });

  it("lands non-2xx replies in the error state (401, 500, …)", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("", { status: 401 })),
    );

    const { result } = renderHook(() => useStartGame());
    await act(() => result.current.start("expired-token", "k"));

    expect(result.current.request).toEqual({ status: "error" });
  });

  it("lands network rejections in the same error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError("network down")),
    );

    const { result } = renderHook(() => useStartGame());
    await act(() => result.current.start("jwt-token", "k"));

    expect(result.current.request).toEqual({ status: "error" });
  });

  it("guards against a double submit — two clicks mint one run", async () => {
    let releaseFirst!: (r: Response) => void;
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockReturnValue(new Promise((resolve) => (releaseFirst = resolve)));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useStartGame());
    let first!: Promise<void>;
    act(() => {
      first = result.current.start("jwt-token", "k");
      void result.current.start("jwt-token", "k"); // second click, in flight
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    releaseFirst(startedResponse("run-1"));
    await act(() => first);
    await waitFor(() =>
      expect(result.current.request).toEqual({
        status: "started",
        gameId: "run-1",
      }),
    );
  });

  it("reset returns to idle so a New Run can mint afresh", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(startedResponse("run-1")),
    );
    const { result } = renderHook(() => useStartGame());
    await act(() => result.current.start("jwt-token", "k"));

    act(() => result.current.reset());
    expect(result.current.request).toEqual({ status: "idle" });
  });
});
