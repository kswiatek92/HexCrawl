/**
 * `useStartGame` — the HTTP half of the run lifecycle (task 5.12), beside its
 * WS half (`useGameSocket`): `POST /api/v1/game/start` with the Supabase
 * bearer token mints a run, and the returned `game_id` is the `sessionId`
 * the socket then connects with.
 *
 * Follows the 5.10 data-fetching convention (raw `fetch`, explicit
 * discriminated-union request state) with one deliberate difference: this is
 * a *mutation*, so the request fires from an event handler (`start()`), not
 * an effect — there is no mount-time fetch, no dependency array, and no
 * abort-on-cleanup dance. What replaces them is a double-submit guard (two
 * clicks must not mint two runs) read through a ref, so the guard sees the
 * in-flight truth even before the state lands.
 *
 * The token is a parameter, not a store read: the caller (`GameScreen`, behind
 * `RequireAuth`) owns *when* auth is ready; this hook stays a pure transport.
 */

import { useCallback, useRef, useState } from "react";
import type { StartGameResponse } from "../types/gameState";

/** Fallback when an email yields no usable name (e.g. "@host"). */
const DEFAULT_PLAYER_NAME = "player";

/** Backend bound: `StartGameRequest.player_name` is `max_length=32`. */
const MAX_PLAYER_NAME_LENGTH = 32;

/**
 * Derive the run's `player_name` from the signed-in email: the local part,
 * clamped to the backend's 32-char bound. There is no profile/display-name
 * feature yet (the leaderboard shows truncated user ids), so the email local
 * part is the friendliest name the client actually has. Pure, exported for
 * tests.
 */
export function playerNameFromEmail(email: string | undefined): string {
  const localPart = (email ?? "").split("@")[0].trim();
  if (localPart === "") return DEFAULT_PLAYER_NAME;
  return localPart.slice(0, MAX_PLAYER_NAME_LENGTH);
}

/** The request lifecycle, one variant per renderable state (5.10 doctrine). */
export type StartGameRequestState =
  | { status: "idle" }
  | { status: "starting" }
  | { status: "error" }
  | { status: "started"; gameId: string };

export interface UseStartGameResult {
  request: StartGameRequestState;
  /** Mint a new run. No-ops while one is already being minted. */
  start: (token: string, playerName: string) => Promise<void>;
  /** Back to `idle` (a New Run discards the finished run's id first). */
  reset: () => void;
}

export function useStartGame(): UseStartGameResult {
  const [request, setRequest] = useState<StartGameRequestState>({
    status: "idle",
  });
  // The guard reads a ref, not `request`: two synchronous clicks would both
  // see the stale pre-setState value, but the ref flips before the first
  // await — so the second click no-ops.
  const inFlight = useRef(false);

  const start = useCallback(async (token: string, playerName: string) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setRequest({ status: "starting" });
    try {
      const res = await fetch("/api/v1/game/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ player_name: playerName }),
      });
      if (!res.ok) {
        throw new Error(`start-game failed: ${res.status}`);
      }
      const body = (await res.json()) as StartGameResponse;
      setRequest({ status: "started", gameId: body.game_id });
    } catch {
      // Network failure and non-2xx land in the same renderable error state;
      // the screen offers retry (an event handler resets + restarts).
      setRequest({ status: "error" });
    } finally {
      inFlight.current = false;
    }
  }, []);

  const reset = useCallback(() => {
    setRequest({ status: "idle" });
  }, []);

  return { request, start, reset };
}
