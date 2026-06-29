/**
 * `useKeyboardInput` — the input edge of the WebSocket turn loop (task 5.7).
 *
 * Translates physical key presses into `ClientAction` frames and drives them
 * through the `sendAction` returned by `useGameSocket` (5.6). The movement keys
 * (WASD / arrows) cover both walking *and* combat: the domain auto-resolves a
 * move-into-enemy as an attack (`src/domain/services/game_service.py`), so the
 * four cardinals are all the turn loop needs to be drivable. Space passes the
 * turn (`wait`).
 *
 * Split like the rest of the frontend (pure fn + effect hook, mirroring
 * `buildGameSocketUrl` / `useGameSocket`): `keyToAction` is a pure, exhaustively
 * testable map, and the hook owns the `window` listener lifecycle.
 *
 * Wire contract: `ClientAction` in `types/socket.ts`, mirroring
 * `src/entrypoints/ws/protocol.py`. `Direction` orientation is fixed by the
 * domain (`NORTH=(0,-1)` up, `SOUTH=(0,+1)` down, `EAST=(+1,0)` right,
 * `WEST=(-1,0)` left), so arrows/WASD map to screen directions the obvious way.
 */

import { useEffect, useRef } from "react";
import type { ClientAction } from "../types/socket";

/**
 * Map a `KeyboardEvent.key` to the action it triggers, or `null` if the key is
 * unbound. Pure — no DOM, no socket — so the whole binding table is unit-tested
 * in isolation. WASD and arrows are aliases for the same four cardinals; space
 * is the bare `wait`.
 */
export function keyToAction(key: string): ClientAction | null {
  switch (key) {
    case "ArrowUp":
    case "w":
    case "W":
      return { action: "move", direction: "NORTH" };
    case "ArrowDown":
    case "s":
    case "S":
      return { action: "move", direction: "SOUTH" };
    case "ArrowLeft":
    case "a":
    case "A":
      return { action: "move", direction: "WEST" };
    case "ArrowRight":
    case "d":
    case "D":
      return { action: "move", direction: "EAST" };
    case " ":
      return { action: "wait" };
    default:
      return null;
  }
}

interface UseKeyboardInputOptions {
  /** Attach the listener while `true` (default). Set `false` to mute input. */
  enabled?: boolean;
}

/**
 * Don't capture game keys while the user is typing into a form control — guards
 * future login/leaderboard inputs from being hijacked by WASD/space.
 */
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

/**
 * Attach a window-level `keydown` listener that maps each press to a
 * `ClientAction` and sends it. The listener is bound once (keyed on `enabled`)
 * and reads `sendAction` through a ref refreshed every render, so it always
 * calls the latest function without re-binding — robust even if the caller
 * passes a non-memoised `sendAction`.
 */
export function useKeyboardInput(
  sendAction: (action: ClientAction) => void,
  { enabled = true }: UseKeyboardInputOptions = {},
): void {
  const sendActionRef = useRef(sendAction);
  sendActionRef.current = sendAction;

  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      // One turn per physical press: drop OS key-repeat so a held key can't
      // flood the socket with a turn per repeat tick.
      if (event.repeat) return;
      if (isEditableTarget(event.target)) return;
      // Leave modifier chords to the browser/OS — Ctrl+W (close tab), Cmd+W,
      // Alt+← (back) etc. must not be hijacked as movement or preventDefault'd.
      // (Shift is left alone: it's not a standalone shortcut modifier.)
      if (event.ctrlKey || event.metaKey || event.altKey) return;

      const action = keyToAction(event.key);
      if (action === null) return;

      // Stop the browser scrolling on arrows/space now that the key is ours.
      event.preventDefault();
      sendActionRef.current(action);
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled]);
}
