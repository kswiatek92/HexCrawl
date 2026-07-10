/**
 * The leaderboard page (task 5.10) — global + weekly tabs over the public
 * boards (`GET /v1/leaderboard/{global,weekly}`, tasks 3.10/3.11).
 *
 * Every request state renders explicitly — loading, error (with retry),
 * empty, and the ranked table — because the state machine `useLeaderboard`
 * returns has no other way to be consumed (QUIZZES.md 5.10 Q2). The active
 * tab is plain local state: switching period re-runs the hook's effect, and
 * the abort-on-cleanup in the hook keeps a slow stale response from
 * clobbering the tab you're now on.
 *
 * Rows show the score plus its inputs (floors, kills) — the same "score and
 * how it was reached" breakdown the wire carries (`LeaderboardEntry`).
 * Attribution is a truncated opaque UUID until profiles/display names exist.
 */

import { useState } from "react";
import type { LeaderboardEntry, LeaderboardPeriod } from "../types/leaderboard";
import {
  LEADERBOARD_TABS,
  formatComputedAt,
  formatPlayerId,
} from "./leaderboardModel";
import { useLeaderboard } from "./useLeaderboard";

function Row({ entry }: { entry: LeaderboardEntry }) {
  return (
    <tr data-testid="leaderboard-row" className="border-b border-slate-800">
      <td className="px-3 py-2 font-mono text-slate-400">{entry.rank}</td>
      <td className="px-3 py-2 font-mono">{formatPlayerId(entry.user_id)}</td>
      <td className="px-3 py-2 text-right font-mono font-semibold text-emerald-400">
        {entry.value}
      </td>
      <td className="px-3 py-2 text-right font-mono">{entry.floors_reached}</td>
      <td className="px-3 py-2 text-right font-mono">{entry.kills}</td>
      <td className="px-3 py-2 font-mono text-slate-400">
        {formatComputedAt(entry.computed_at)}
      </td>
    </tr>
  );
}

function Board({ period }: { period: LeaderboardPeriod }) {
  const { query, retry } = useLeaderboard(period);

  switch (query.status) {
    case "loading":
      return (
        <p data-testid="leaderboard-loading" className="text-slate-400">
          Loading standings…
        </p>
      );
    case "error":
      return (
        <div data-testid="leaderboard-error" className="space-y-2">
          <p className="text-amber-400">Could not load the leaderboard.</p>
          <button
            type="button"
            onClick={retry}
            className="rounded bg-slate-700 px-3 py-1 font-semibold text-slate-100 hover:bg-slate-600"
          >
            Retry
          </button>
        </div>
      );
    case "success":
      if (query.entries.length === 0) {
        return (
          <p data-testid="leaderboard-empty" className="text-slate-400">
            No scores yet — be the first on the board.
          </p>
        );
      }
      return (
        <table className="w-full max-w-2xl border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-600 text-slate-400">
              <th scope="col" className="px-3 py-2 font-semibold">
                #
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                Player
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                Score
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                Floors
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                Kills
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                Date
              </th>
            </tr>
          </thead>
          <tbody>
            {query.entries.map((entry) => (
              <Row key={entry.rank} entry={entry} />
            ))}
          </tbody>
        </table>
      );
  }
}

export default function Leaderboard() {
  const [period, setPeriod] = useState<LeaderboardPeriod>("GLOBAL");

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-bold">Leaderboard</h1>

      <div
        role="tablist"
        aria-label="Leaderboard period"
        className="flex gap-2"
      >
        {LEADERBOARD_TABS.map((tab) => {
          const active = tab.period === period;
          return (
            <button
              key={tab.period}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setPeriod(tab.period)}
              className={`rounded px-4 py-1.5 font-semibold ${
                active
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-800 text-slate-300 hover:text-white"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Keyed by period so each tab mounts its own Board — state never bleeds
          between boards, and the hook's cleanup aborts the outgoing fetch. */}
      <Board key={period} period={period} />
    </section>
  );
}
