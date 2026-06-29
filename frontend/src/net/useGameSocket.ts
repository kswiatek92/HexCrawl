/**
 * `useGameSocket` — the client half of the WebSocket turn loop (task 5.6).
 *
 * Owns the socket *lifecycle* for one run: open it, run the first-message auth
 * handshake, dispatch inbound frames into the Zustand store, and close on
 * cleanup. The render/update split mirrors the backend's: declarative state
 * (`status` / `gameState`) flows into the store so the canvas can subscribe,
 * while the imperative `sendAction` is returned for the keyboard handler (5.7).
 *
 * Why an effect + ref (and not socket-in-state): the socket is a long-lived
 * side-effecting object, not render data. It's created in `useEffect` (which has
 * a cleanup phase to close it) and held in a `useRef` so `sendAction` can reach
 * the *current* socket without re-subscribing. React 19 StrictMode runs the
 * effect mount→unmount→mount in dev; the cleanup closes the first socket, so the
 * double-run self-heals instead of leaking a connection.
 *
 * Wire contract: `src/entrypoints/ws/router_game.py` + `protocol.py`, typed in
 * `types/socket.ts`. Connects through the `/ws` path so Vite's dev proxy carries
 * it to the backend single-origin (`vite.config.ts`) — never a hardcoded origin.
 */

import { useCallback, useEffect, useRef } from "react";
import { useGameStore } from "../store/gameStore";
import type { ClientAction, ServerFrame } from "../types/socket";

interface UseGameSocketParams {
  /** The run id (`Dungeon.dungeon_id`). `null` until a run is started. */
  sessionId: string | null;
  /** The Supabase access-token JWT. `null` until the user is authenticated. */
  token: string | null;
}

interface UseGameSocketResult {
  /** Send one action to drive a turn. No-ops if the socket isn't open yet. */
  sendAction: (action: ClientAction) => void;
}

/**
 * Build the turn-loop socket URL for a run. Pure (location injected) so it's
 * unit-testable: picks `wss:` on an HTTPS page, `ws:` otherwise, keeps the
 * page's host (the dev proxy / prod ALB lives there), and targets `/ws/game/`.
 */
export function buildGameSocketUrl(
  sessionId: string,
  location: Pick<Location, "protocol" | "host">,
): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws/game/${sessionId}`;
}

export function useGameSocket({
  sessionId,
  token,
}: UseGameSocketParams): UseGameSocketResult {
  const socketRef = useRef<WebSocket | null>(null);
  const setStatus = useGameStore((s) => s.setStatus);
  const setGameState = useGameStore((s) => s.setGameState);

  useEffect(() => {
    // Nothing to connect to until a run exists and the user is authenticated;
    // the hook can still be mounted unconditionally (hooks rules) before then.
    if (sessionId === null || token === null) return;

    const socket = new WebSocket(
      buildGameSocketUrl(sessionId, window.location),
    );
    socketRef.current = socket;
    setStatus("connecting");

    socket.onopen = () => {
      // First-message auth: the server awaits this before any action frame.
      socket.send(JSON.stringify({ type: "auth", token }));
    };

    socket.onmessage = (event: MessageEvent) => {
      let frame: ServerFrame;
      try {
        frame = JSON.parse(event.data as string) as ServerFrame;
      } catch {
        // A non-JSON frame can't be acted on; drop it rather than crash the loop.
        return;
      }
      switch (frame.type) {
        case "connected":
          setStatus("open");
          setGameState(frame.state);
          break;
        case "turn":
          setGameState(frame.state);
          // `game_over` ends the run server-side with a 1000 close, which lands
          // in `onclose` below; no extra client action needed here.
          break;
        case "error":
          // Recoverable bad-message reply — leave `gameState` untouched.
          break;
      }
    };

    socket.onclose = () => {
      setStatus("closed");
    };

    return () => {
      socketRef.current = null;
      socket.close();
    };
  }, [sessionId, token, setStatus, setGameState]);

  const sendAction = useCallback((action: ClientAction) => {
    const socket = socketRef.current;
    if (socket === null || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify(action));
  }, []);

  return { sendAction };
}
