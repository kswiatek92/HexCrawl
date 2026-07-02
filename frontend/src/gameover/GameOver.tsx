/**
 * The game-over screen (task 5.9) — a DOM overlay over the canvas, shown when
 * the run's state machine reaches `game_over` (see `gameStore.ts`).
 *
 * **HTML over canvas**, like the HUD (5.8): the final world frame stays
 * visible underneath — the classic roguelike death screen — and the text is
 * crisp DOM, not pixels in the 240×160 buffer. An overlay, not a route: a
 * deep-linkable `/game-over` URL with no run behind it would be meaningless.
 *
 * **No score is shown** — score is a game-over computation *server-side*
 * (`SubmitScore`); it never crosses the WS. The screen shows the run's score
 * inputs (floor 1-based, kills, turns) and points at the leaderboard, where
 * the computed score lands — for deaths only, since an abandoned run scores
 * nothing (task 3.3).
 *
 * "New Run" only resets the store to `idle` for now: actual start-game
 * (POST /game/start) arrives with 5.11/5.12, the same dormant seam as the
 * socket's `sessionId: null`.
 */

import { Link } from "react-router-dom";
import { useGameStore } from "../store/gameStore";
import { gameOverSubtitle, gameOverTitle } from "./gameOverModel";

function FinalStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between gap-8">
      <dt className="text-slate-400">{label}</dt>
      <dd
        data-testid={`gameover-${label.toLowerCase()}`}
        className="font-mono text-slate-100"
      >
        {value}
      </dd>
    </div>
  );
}

export default function GameOver() {
  const phase = useGameStore((s) => s.phase);
  const cause = useGameStore((s) => s.gameOverCause);
  const gameState = useGameStore((s) => s.gameState);
  const kills = useGameStore((s) => s.kills);
  const resetRun = useGameStore((s) => s.resetRun);

  // The machine guarantees cause/gameState are set in game_over; the guards
  // keep the impossible states unrenderable rather than half-painted.
  if (phase !== "game_over" || cause === null || gameState === null) {
    return null;
  }

  return (
    <div
      data-testid="gameover"
      className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/80"
    >
      <section className="w-72 space-y-4 rounded border border-slate-700 bg-slate-900 p-6 text-center text-sm">
        <header className="space-y-1">
          <h2
            data-testid="gameover-title"
            className={`text-2xl font-bold tracking-widest ${
              cause === "died" ? "text-red-500" : "text-amber-400"
            }`}
          >
            {gameOverTitle(cause)}
          </h2>
          <p className="text-slate-400">{gameOverSubtitle(cause)}</p>
        </header>

        <dl className="space-y-1 text-left">
          {/* 0-based engine index → 1-based display, the leaderboard convention. */}
          <FinalStat label="Floor" value={gameState.current_floor_index + 1} />
          <FinalStat label="Kills" value={kills} />
          <FinalStat label="Turns" value={gameState.turn_count} />
        </dl>

        {cause === "died" && (
          <p className="text-xs text-slate-400">
            Your score is computed on the{" "}
            <Link
              to="/leaderboard"
              className="text-emerald-400 underline hover:text-emerald-300"
            >
              leaderboard
            </Link>
            .
          </p>
        )}

        <button
          type="button"
          onClick={resetRun}
          className="w-full rounded bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-500"
        >
          New Run
        </button>
      </section>
    </div>
  );
}
