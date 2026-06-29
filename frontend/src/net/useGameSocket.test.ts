import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildGameSocketUrl, useGameSocket } from "./useGameSocket";
import { useGameStore } from "../store/gameStore";
import type { GameStateView } from "../types/gameState";

/**
 * jsdom ships no `WebSocket`, so the hook's lifecycle is exercised against this
 * fake: it records the URL and every frame `send()`, and exposes drivers
 * (`open` / `receive` / `fireClose`) so a test can step the socket through its
 * states. `WebSocket.OPEN` inside the hook resolves to this class's static
 * `OPEN` once it's stubbed onto the global.
 */
class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = MockWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
  });

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  /** Drive: the connection opens. */
  open(): void {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  /** Drive: the server pushes a frame. */
  receive(frame: unknown): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  /** Drive: the server pushes a raw (possibly non-JSON) payload. */
  receiveRaw(data: string): void {
    this.onmessage?.({ data });
  }

  /** Drive: the connection closes. */
  fireClose(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

const sampleState = (x: number, y: number): GameStateView => ({
  player: { position: [x, y] },
  floor: {
    width: 1,
    height: 1,
    tiles: [["FLOOR"]],
    enemies: [],
    items: {},
    stairs_down: [0, 0],
  },
});

const lastSocket = (): MockWebSocket => {
  const ws = MockWebSocket.instances.at(-1);
  if (!ws) throw new Error("no socket was opened");
  return ws;
};

const initialStore = useGameStore.getState();

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  useGameStore.setState(initialStore, true);
});

describe("buildGameSocketUrl", () => {
  it("uses ws:// and the page host over plain HTTP", () => {
    expect(
      buildGameSocketUrl("abc", { protocol: "http:", host: "localhost:5173" }),
    ).toBe("ws://localhost:5173/ws/game/abc");
  });

  it("upgrades to wss:// on an HTTPS page", () => {
    expect(
      buildGameSocketUrl("abc", { protocol: "https:", host: "hexcrawl.io" }),
    ).toBe("wss://hexcrawl.io/ws/game/abc");
  });
});

describe("useGameSocket", () => {
  it("opens no socket until both session and token are present", () => {
    renderHook(() => useGameSocket({ sessionId: null, token: null }));
    expect(MockWebSocket.instances).toHaveLength(0);
    expect(useGameStore.getState().status).toBe("idle");
  });

  it("opens the run socket and sends the auth frame on open", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt-123" }));

    const ws = lastSocket();
    expect(ws.url.startsWith("ws://")).toBe(true);
    expect(ws.url.endsWith("/ws/game/game-1")).toBe(true);
    expect(useGameStore.getState().status).toBe("connecting");
    expect(ws.sent).toHaveLength(0);

    act(() => ws.open());
    expect(ws.sent).toEqual([
      JSON.stringify({ type: "auth", token: "jwt-123" }),
    ]);
  });

  it("a connected frame opens the status and stores the state", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    const state = sampleState(2, 3);

    act(() => ws.open());
    act(() => ws.receive({ type: "connected", game_id: "game-1", state }));

    expect(useGameStore.getState().status).toBe("open");
    expect(useGameStore.getState().gameState).toEqual(state);
  });

  it("a turn frame replaces the stored state (game_over included)", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    act(() => ws.open());

    const mid = sampleState(4, 4);
    act(() =>
      ws.receive({ type: "turn", events: [], state: mid, game_over: false }),
    );
    expect(useGameStore.getState().gameState).toEqual(mid);

    const final = sampleState(5, 5);
    act(() =>
      ws.receive({ type: "turn", events: [], state: final, game_over: true }),
    );
    expect(useGameStore.getState().gameState).toEqual(final);
  });

  it("an error frame leaves the stored state untouched", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    const state = sampleState(1, 1);

    act(() => ws.open());
    act(() => ws.receive({ type: "connected", game_id: "game-1", state }));
    act(() => ws.receive({ type: "error", detail: "unknown action 'jump'" }));

    expect(useGameStore.getState().gameState).toEqual(state);
  });

  it("a non-JSON frame is dropped without crashing the loop", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    const state = sampleState(1, 1);

    act(() => ws.open());
    act(() => ws.receive({ type: "connected", game_id: "game-1", state }));
    act(() => ws.receiveRaw("not json{"));

    expect(useGameStore.getState().status).toBe("open");
    expect(useGameStore.getState().gameState).toEqual(state);
  });

  it("sendAction frames the action only once the socket is open", () => {
    const { result } = renderHook(() =>
      useGameSocket({ sessionId: "game-1", token: "jwt" }),
    );
    const ws = lastSocket();

    // Not open yet: the action is dropped, not thrown.
    act(() => result.current.sendAction({ action: "wait" }));
    expect(ws.sent).toHaveLength(0);

    act(() => ws.open()); // sends the auth frame (sent[0])
    act(() =>
      result.current.sendAction({ action: "move", direction: "NORTH" }),
    );
    expect(ws.sent).toContain(
      JSON.stringify({ action: "move", direction: "NORTH" }),
    );
  });

  it("marks the status closed when the socket closes", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();

    act(() => ws.open());
    act(() => ws.fireClose());

    expect(useGameStore.getState().status).toBe("closed");
  });

  it("closes the socket on unmount", () => {
    const { unmount } = renderHook(() =>
      useGameSocket({ sessionId: "game-1", token: "jwt" }),
    );
    const ws = lastSocket();

    unmount();
    expect(ws.close).toHaveBeenCalled();
  });

  it("blanks any prior run's state when starting to connect", () => {
    // Seed the store as if a previous run had left state behind.
    act(() => useGameStore.getState().setGameState(sampleState(9, 9)));

    renderHook(() => useGameSocket({ sessionId: "game-2", token: "jwt" }));

    expect(useGameStore.getState().gameState).toBeNull();
  });

  it("ignores a stale socket's late frames after unmount", () => {
    const { unmount } = renderHook(() =>
      useGameSocket({ sessionId: "game-1", token: "jwt" }),
    );
    const ws = lastSocket();
    const state = sampleState(2, 2);

    act(() => ws.open());
    act(() => ws.receive({ type: "connected", game_id: "game-1", state }));
    expect(useGameStore.getState().status).toBe("open");

    unmount();

    // A message and a close that arrive after cleanup must not write the store
    // for a connection that is no longer active.
    act(() =>
      ws.receive({
        type: "turn",
        events: [],
        state: sampleState(7, 7),
        game_over: false,
      }),
    );
    act(() => ws.fireClose());

    expect(useGameStore.getState().status).toBe("open");
    expect(useGameStore.getState().gameState).toEqual(state);
  });
});
