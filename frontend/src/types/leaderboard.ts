/**
 * TypeScript mirror of the backend leaderboard wire shape.
 *
 * Source of truth is the Pydantic contract in
 * `src/entrypoints/http/schemas.py` (`LeaderboardResponse` /
 * `LeaderboardEntry`), served by `GET /v1/leaderboard/global` (task 3.10) and
 * `GET /v1/leaderboard/weekly` (3.11). Unlike `gameState.ts` this mirrors the
 * entry in full — the page renders every field. `MyScoresResponse`
 * (`/leaderboard/me`) stays untyped until the authed board ships (5.11/5.12).
 */

/** The two `LeaderboardPeriod` enum values, as their wire strings (StrEnum). */
export type LeaderboardPeriod = "GLOBAL" | "WEEKLY";

/**
 * One ranked row. `rank` is absolute (1-indexed, offset-aware server-side);
 * `user_id` is an opaque UUID — `Score` carries no display name in v1, so the
 * UI truncates it for attribution. `computed_at` is an ISO datetime string.
 */
export interface LeaderboardEntry {
  rank: number;
  user_id: string;
  value: number;
  floors_reached: number;
  kills: number;
  computed_at: string;
}

/** A page of one board: the period queried and its ranked entries. */
export interface LeaderboardResponse {
  period: LeaderboardPeriod;
  entries: LeaderboardEntry[];
}
