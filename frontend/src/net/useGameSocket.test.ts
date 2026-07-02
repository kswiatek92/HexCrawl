import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildGameSocketUrl,
  countKills,
  gameOverCause,
  useGameSocket,
} from "./useGameSocket";
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
  current_floor_index: 0,
  turn_count: 0,
  player: {
    name: "Hero",
    position: [x, y],
    hp: 20,
    max_hp: 20,
    attack: 3,
    defense: 1,
  },
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

describe("countKills", () => {
  it("counts only enemy_killed events", () => {
    expect(
      countKills([
        { type: "player_moved", from: [0, 0], to: [1, 0] },
        { type: "enemy_killed", enemy_id: "e1" },
        { type: "player_damaged", amount: 2 },
        { type: "enemy_killed", enemy_id: "e2" },
      ]),
    ).toBe(2);
  });

  it("returns 0 for an empty narrative", () => {
    expect(countKills([])).toBe(0);
  });
});

describe("gameOverCause", () => {
  it("reads an abandoned run from its run_abandoned event", () => {
    expect(gameOverCause([{ type: "run_abandoned" }])).toBe("abandoned");
  });

  it("reads a death from its player_died event", () => {
    expect(
      gameOverCause([{ type: "player_damaged", amount: 5 }, { type: "player_died" }]),
    ).toBe("died");
  });

  it("falls back to died when the narrative names no ending", () => {
    expect(gameOverCause([])).toBe("died");
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

  it("a final turn frame drives the run phase to game_over with its cause", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: "connected",
        game_id: "game-1",
        state: sampleState(0, 0),
      }),
    );
    expect(useGameStore.getState().phase).toBe("playing");

    act(() =>
      ws.receive({
        type: "turn",
        events: [
          { type: "player_damaged", amount: 7 },
          { type: "player_died" },
        ],
        state: sampleState(1, 0),
        game_over: true,
      }),
    );

    expect(useGameStore.getState().phase).toBe("game_over");
    expect(useGameStore.getState().gameOverCause).toBe("died");
  });

  it("an abandoned run's final frame records the abandoned cause", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: "connected",
        game_id: "game-1",
        state: sampleState(0, 0),
      }),
    );

    act(() =>
      ws.receive({
        type: "turn",
        events: [{ type: "run_abandoned" }],
        state: sampleState(0, 0),
        game_over: true,
      }),
    );

    expect(useGameStore.getState().phase).toBe("game_over");
    expect(useGameStore.getState().gameOverCause).toBe("abandoned");
  });

  it("an ordinary turn frame leaves the run phase in playing", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: "connected",
        game_id: "game-1",
        state: sampleState(0, 0),
      }),
    );

    act(() =>
      ws.receive({
        type: "turn",
        // A death-less narrative with a kill: still not a game over.
        events: [{ type: "enemy_killed", enemy_id: "e1" }],
        state: sampleState(1, 0),
        game_over: false,
      }),
    );

    expect(useGameStore.getState().phase).toBe("playing");
    expect(useGameStore.getState().gameOverCause).toBeNull();
  });

  it("counts enemy_killed events across turn frames into the kills stat", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: "connected",
        game_id: "game-1",
        state: sampleState(0, 0),
      }),
    );
    expect(useGameStore.getState().kills).toBe(0);

    act(() =>
      ws.receive({
        type: "turn",
        events: [
          { type: "player_attacked", enemy_id: "e1", damage: 3, killed: true },
          { type: "enemy_killed", enemy_id: "e1" },
          { type: "enemy_killed", enemy_id: "e2" },
        ],
        state: sampleState(1, 0),
        game_over: false,
      }),
    );
    expect(useGameStore.getState().kills).toBe(2);

    act(() =>
      ws.receive({
        type: "turn",
        events: [{ type: "enemy_killed", enemy_id: "e3" }],
        state: sampleState(2, 0),
        game_over: false,
      }),
    );
    expect(useGameStore.getState().kills).toBe(3);
  });

  it("a fresh connected frame zeroes the previous run's kills", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: "turn",
        events: [{ type: "enemy_killed", enemy_id: "e1" }],
        state: sampleState(1, 1),
        game_over: false,
      }),
    );
    expect(useGameStore.getState().kills).toBe(1);

    act(() =>
      ws.receive({
        type: "connected",
        game_id: "game-1",
        state: sampleState(0, 0),
      }),
    );
    expect(useGameStore.getState().kills).toBe(0);
  });

  it("an error frame stores its detail and leaves the state untouched", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();
    const state = sampleState(1, 1);

    act(() => ws.open());
    act(() => ws.receive({ type: "connected", game_id: "game-1", state }));
    act(() => ws.receive({ type: "error", detail: "unknown action 'jump'" }));

    expect(useGameStore.getState().gameState).toEqual(state);
    expect(useGameStore.getState().lastError).toBe("unknown action 'jump'");
  });

  it("the next successful turn clears a stored error", () => {
    renderHook(() => useGameSocket({ sessionId: "game-1", token: "jwt" }));
    const ws = lastSocket();

    act(() => ws.open());
    act(() => ws.receive({ type: "error", detail: "bad frame" }));
    expect(useGameStore.getState().lastError).toBe("bad frame");

    act(() =>
      ws.receive({
        type: "turn",
        events: [],
        state: sampleState(1, 1),
        game_over: false,
      }),
    );
    expect(useGameStore.getState().lastError).toBeNull();
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

  it("blanks any prior run's state and stats when starting to connect", () => {
    // Seed the store as if a previous run had left state behind.
    act(() => useGameStore.getState().applyTurn(sampleState(9, 9), 6));

    renderHook(() => useGameSocket({ sessionId: "game-2", token: "jwt" }));

    expect(useGameStore.getState().gameState).toBeNull();
    expect(useGameStore.getState().kills).toBe(0);
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
