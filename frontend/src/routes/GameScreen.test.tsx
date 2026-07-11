import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GameScreen from "./GameScreen";
import { useAuthStore } from "../auth/authStore";
import { useGameStore } from "../store/gameStore";
import { makeSession, resetAuthStore } from "../test/fakeSupabase";

/**
 * The 5.12 wiring test: auth session + minted game_id must reach the socket.
 * Only construction is asserted (URL + that it happens post-start), so this
 * stub records instances; driving frames through the loop is
 * useGameSocket.test's job.
 */
class RecordingWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: RecordingWebSocket[] = [];

  url: string;
  readyState = RecordingWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: unknown = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  send = vi.fn();

  constructor(url: string) {
    this.url = url;
    RecordingWebSocket.instances.push(this);
  }
}

function renderGameScreen() {
  return render(
    <MemoryRouter>
      <GameScreen />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  resetAuthStore();
  useGameStore.getState().resetRun();
  useGameStore.getState().setStatus("idle");
  RecordingWebSocket.instances = [];
  vi.stubGlobal("WebSocket", RecordingWebSocket);
});

describe("GameScreen start-run wiring (5.12)", () => {
  it("does not connect the socket before a run is started", () => {
    useAuthStore.getState().setSession(makeSession());
    renderGameScreen();

    expect(screen.getByTestId("start-run")).toBeInTheDocument();
    expect(RecordingWebSocket.instances).toHaveLength(0);
  });

  it("start POSTs with the session's bearer token, then the socket connects with the minted game_id", async () => {
    useAuthStore
      .getState()
      .setSession(makeSession("krzysztof@example.com", "live-jwt"));
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response(JSON.stringify({ game_id: "run-42" }), { status: 201 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    renderGameScreen();
    await userEvent.click(screen.getByTestId("start-run"));

    // The HTTP half: token attached, player_name derived from the email.
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/game/start",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer live-jwt" }),
        body: JSON.stringify({ player_name: "krzysztof" }),
      }),
    );

    // The WS half: the previously dormant seam connects with the run's id.
    await waitFor(() => expect(RecordingWebSocket.instances).toHaveLength(1));
    expect(RecordingWebSocket.instances[0].url).toContain("/ws/game/run-42");
  });

  it("renders the error state with a retry when the start fails", async () => {
    useAuthStore.getState().setSession(makeSession());
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("", { status: 500 })),
    );

    renderGameScreen();
    await userEvent.click(screen.getByTestId("start-run"));

    expect(await screen.findByTestId("start-run-error")).toBeInTheDocument();
    expect(RecordingWebSocket.instances).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
