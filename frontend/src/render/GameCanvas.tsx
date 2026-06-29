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
import { loadPlayerSprite } from "./playerSprite";
import {
  PLAYER_FRAME_COUNT,
  PLAYER_FRAME_DURATION_MS,
} from "./playerAnimation";

interface GameCanvasProps {
  /** Current game state to paint, or `null` before a run exists (task 5.6). */
  gameState: GameStateView | null;
}

export default function GameCanvas({ gameState }: GameCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The render loop reads state from here, never from the closure — so a new
  // prop just updates a ref instead of restarting the loop.
  const stateRef = useRef<GameStateView | null>(gameState);
  // Per-frame animation state. A ref, not state: it mutates every animation step
  // and must NOT trigger a re-render (QUIZZES.md 5.4 — ref for mutable values the
  // UI is not derived from, state for values it is).
  const animRef = useRef({ frame: 0, lastFrameTime: 0 });

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
    // The player sprite is authored at 32px but drawn at 16px; nearest-neighbour
    // keeps that downscale crisp instead of blurry. Set once for the context.
    ctx.imageSmoothingEnabled = false;

    let rafId = 0;
    let cancelled = false;
    let tiles: TileImages | null = null;
    let playerSprite: HTMLImageElement | null = null;

    const loop = (timestamp: number) => {
      if (cancelled || tiles === null || playerSprite === null) return;
      const anim = animRef.current;
      // Advance the bob frame on its own cadence, independent of the (faster) rAF
      // rate — step when at least one frame's worth of time has elapsed.
      if (timestamp - anim.lastFrameTime >= PLAYER_FRAME_DURATION_MS) {
        anim.frame = (anim.frame + 1) % PLAYER_FRAME_COUNT;
        anim.lastFrameTime = timestamp;
      }
      drawFloor(ctx, stateRef.current, tiles, playerSprite, anim.frame);
      rafId = requestAnimationFrame(loop);
    };

    // Every sprite must be decoded before the first paint (a half-loaded set would
    // draw gaps); start the loop once both the tiles and the player are ready.
    Promise.all([loadTileImages(), loadPlayerSprite()])
      .then(([loadedTiles, loadedPlayer]) => {
        if (cancelled) return;
        tiles = loadedTiles;
        playerSprite = loadedPlayer;
        rafId = requestAnimationFrame(loop);
      })
      .catch((error: unknown) => {
        // A failed decode (bad bundle path, transient cache miss) must not become
        // an unhandled rejection that silently leaves the loop unstarted.
        if (!cancelled) console.error("Failed to load sprites", error);
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
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
