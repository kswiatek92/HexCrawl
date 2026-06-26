/**
 * The canvas renderer component.
 *
 * Owns the `<canvas>` element, its GBA-native backing buffer, and the render
 * loop. Two deliberate seams:
 *
 *  - **`requestAnimationFrame` loop** (not `setInterval`): the browser schedules
 *    frames in step with the display refresh and pauses them on a hidden tab —
 *    "let the platform schedule the work" (QUIZZES.md 5.3 Q1).
 *  - **Render decoupled from state** (QUIZZES.md 5.3 Q2): the loop draws the
 *    *current* state read from a ref; a React state/prop change just refreshes
 *    that ref. The draw cadence (rAF) is independent of the update cadence
 *    (turns over the WS, wired in task 5.6). UI = function of state.
 */

import { useEffect, useRef } from "react";
import type { GameStateView } from "../types/gameState";
import { BACKING_HEIGHT, BACKING_WIDTH, SCALE } from "./camera";
import { drawFloor } from "./drawFloor";
import { loadTileImages, type TileImages } from "./tileSet";

interface GameCanvasProps {
  /** Current game state to paint, or `null` before a run exists (task 5.6). */
  gameState: GameStateView | null;
}

export default function GameCanvas({ gameState }: GameCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The render loop reads state from here, never from the closure — so a new
  // prop just updates a ref instead of restarting the loop.
  const stateRef = useRef<GameStateView | null>(gameState);

  useEffect(() => {
    stateRef.current = gameState;
  }, [gameState]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    // jsdom (and any context-less environment) returns null — there's nothing to
    // draw into, so skip the loop entirely rather than guard every frame.
    if (!ctx) return;

    let frame = 0;
    let cancelled = false;
    let images: TileImages | null = null;

    const loop = () => {
      if (cancelled || images === null) return;
      drawFloor(ctx, stateRef.current, images);
      frame = requestAnimationFrame(loop);
    };

    // Tiles must all be decoded before the first paint; start the loop once.
    loadTileImages()
      .then((loaded) => {
        if (cancelled) return;
        images = loaded;
        frame = requestAnimationFrame(loop);
      })
      .catch((error: unknown) => {
        // A failed tile decode (bad bundle path, transient cache miss) must not
        // become an unhandled rejection that silently leaves the loop unstarted.
        if (!cancelled) console.error("Failed to load tile sprites", error);
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      width={BACKING_WIDTH}
      height={BACKING_HEIGHT}
      // Fixed integer ×SCALE (720×480) for crisp pixels. Responsive
      // largest-fit scaling is deferred to the HUD/layout pass (task 5.8).
      style={{
        width: BACKING_WIDTH * SCALE,
        height: BACKING_HEIGHT * SCALE,
        imageRendering: "pixelated",
      }}
      data-testid="game-canvas"
    />
  );
}
