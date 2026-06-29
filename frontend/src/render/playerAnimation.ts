/**
 * Player idle-animation math: which vertical offset to draw the sprite at.
 *
 * Pure module — no DOM, no canvas, no timers. The player draft is a single static
 * frame, so the "animation" is a gentle vertical bob: the sprite hops up by a pixel
 * and back on a fixed cadence. The frame index is owned by the render loop
 * (`GameCanvas`, in a `useRef`); this module just maps a frame to its pixel offset.
 *
 * Movement (tile-to-tile tween) is a later concern — it needs live position changes,
 * which arrive with the WebSocket (task 5.6) and keyboard input (task 5.7).
 */

/** Vertical offset per frame, in backing-buffer pixels. A 2-frame up/down bob. */
export const PLAYER_BOB_OFFSETS_PX = [0, -1] as const;

/** Number of distinct animation frames. */
export const PLAYER_FRAME_COUNT = PLAYER_BOB_OFFSETS_PX.length;

/** How long each frame is held, in milliseconds. */
export const PLAYER_FRAME_DURATION_MS = 350;

/**
 * The vertical bob offset (px) for a frame index. Wraps modulo the frame count, so
 * a caller can keep a monotonically increasing counter without bounding it itself.
 */
export function bobOffsetForFrame(frame: number): number {
  const wrapped =
    ((frame % PLAYER_FRAME_COUNT) + PLAYER_FRAME_COUNT) % PLAYER_FRAME_COUNT;
  return PLAYER_BOB_OFFSETS_PX[wrapped];
}
