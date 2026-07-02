/**
 * Pure game-over display model — no React, mirroring the `hudModel.ts` split:
 * the component file exports only the component (fast-refresh friendly), and
 * the logic here is unit-testable without rendering.
 */

import type { GameOverCause } from "../store/gameStore";

/** The screen's headline, by how the run ended. */
export function gameOverTitle(cause: GameOverCause): string {
  return cause === "abandoned" ? "RUN ABANDONED" : "GAME OVER";
}

/** One line of epitaph under the headline, by how the run ended. */
export function gameOverSubtitle(cause: GameOverCause): string {
  return cause === "abandoned"
    ? "You fled the dungeon. No score is kept for deserters."
    : "The dungeon claims another crawler.";
}
