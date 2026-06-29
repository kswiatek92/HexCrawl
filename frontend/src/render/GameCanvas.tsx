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
import { loadEnemySprites, type EnemySprites } from "./enemySprites";
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
  // UI is not derived from, state for values it is). `lastFrameTime` is null until
  // the first frame seeds it from the rAF clock (see the loop).
  const animRef = useRef<{ frame: number; lastFrameTime: number | null }>({
    frame: 0,
    lastFrameTime: null,
  });

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
    let enemySprites: EnemySprites | null = null;

    const loop = (timestamp: number) => {
      if (
        cancelled ||
        tiles === null ||
        playerSprite === null ||
        enemySprites === null
      )
        return;
      const anim = animRef.current;
      // Seed the clock on the first frame so the bob starts at rest — the rAF
      // timestamp is ms-since-page-load, so comparing against 0 would advance
      // immediately. Then step the bob on its own cadence, independent of the
      // (faster) rAF rate: advance by whole elapsed frames and carry the
      // remainder, so a dropped/paused frame catches up cleanly rather than
      // skewing the cadence.
      if (anim.lastFrameTime === null) anim.lastFrameTime = timestamp;
      const elapsed = timestamp - anim.lastFrameTime;
      if (elapsed >= PLAYER_FRAME_DURATION_MS) {
        const steps = Math.floor(elapsed / PLAYER_FRAME_DURATION_MS);
        anim.frame = (anim.frame + steps) % PLAYER_FRAME_COUNT;
        anim.lastFrameTime += steps * PLAYER_FRAME_DURATION_MS;
      }
      drawFloor(
        ctx,
        stateRef.current,
        tiles,
        playerSprite,
        enemySprites,
        anim.frame,
      );
      rafId = requestAnimationFrame(loop);
    };

    // Every sprite must be decoded before the first paint (a half-loaded set would
    // draw gaps); start the loop once the tiles, player, and enemies are all ready.
    Promise.all([loadTileImages(), loadPlayerSprite(), loadEnemySprites()])
      .then(([loadedTiles, loadedPlayer, loadedEnemies]) => {
        if (cancelled) return;
        tiles = loadedTiles;
        playerSprite = loadedPlayer;
        enemySprites = loadedEnemies;
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
