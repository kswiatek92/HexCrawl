/**
 * Data hook for one leaderboard (task 5.10): fetches the board for a period
 * and exposes an explicit request state machine.
 *
 * **Raw `fetch` in an effect, not React Query/SWR** — a deliberate trade-off:
 * the libraries buy response caching, request dedup, stale-while-revalidate
 * and retries, which two public GET endpoints on a backend-focused portfolio
 * don't yet earn (QUIZZES.md 5.10 Q1). What we must still hand-roll is the
 * part they'd otherwise cover for free:
 *
 *  - **Explicit `loading | error | success` states** as a discriminated union,
 *    so the component physically cannot read entries out of a half-state and
 *    every lifecycle stage gets rendered (QUIZZES.md 5.10 Q2).
 *  - **Stale-response safety**: each (period, attempt) run owns an
 *    `AbortController`; cleanup aborts the in-flight request, so a slow
 *    response for a tab you already left can never clobber the active one.
 *    This is also what makes the effect StrictMode-safe.
 *  - **HTTP errors are errors**: `fetch` resolves on a 500, so `res.ok` is
 *    checked explicitly; network rejections land in the same `error` state.
 */

import { useCallback, useEffect, useState } from "react";
import type {
  LeaderboardEntry,
  LeaderboardPeriod,
  LeaderboardResponse,
} from "../types/leaderboard";
import { leaderboardPath } from "./leaderboardModel";

/** The request lifecycle, one variant per renderable state. */
export type LeaderboardQuery =
  | { status: "loading" }
  | { status: "error" }
  | { status: "success"; entries: LeaderboardEntry[] };

export interface UseLeaderboardResult {
  query: LeaderboardQuery;
  /** Re-run the fetch for the current period (the error screen's Retry). */
  retry: () => void;
}

/**
 * One hook instance serves one period: the state starts at `loading` and only
 * `retry()` resets it, so a caller that can change `period` must remount the
 * consumer (`<Board key={period}>` in `Leaderboard.tsx`) rather than mutate
 * the prop — keeping the effect free of synchronous setState
 * (react-hooks/set-state-in-effect).
 */
export function useLeaderboard(
  period: LeaderboardPeriod,
): UseLeaderboardResult {
  const [query, setQuery] = useState<LeaderboardQuery>({ status: "loading" });
  // Bumped by retry() so the effect re-runs without encoding "how to fetch"
  // anywhere but the effect itself.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    fetch(leaderboardPath(period), { signal: controller.signal })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`leaderboard fetch failed: ${res.status}`);
        }
        return res.json() as Promise<LeaderboardResponse>;
      })
      .then((body) => {
        // Abort only rejects *pending* work — a success handler already queued
        // when cleanup ran would still fire, clobbering a retry's fresh
        // loading state with stale data. Guard both settle paths.
        if (controller.signal.aborted) return;
        setQuery({ status: "success", entries: body.entries });
      })
      .catch(() => {
        // An abort is this effect's own cleanup (tab switched / unmounted),
        // not a failure — and setting state after cleanup would be a leak.
        if (controller.signal.aborted) return;
        setQuery({ status: "error" });
      });

    return () => controller.abort();
  }, [period, attempt]);

  // An event handler, not an effect: resetting to loading here is what keeps
  // the effect itself setState-free on re-run.
  const retry = useCallback(() => {
    setQuery({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return { query, retry };
}
