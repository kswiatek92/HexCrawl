/**
 * Pure leaderboard display model — no React, mirroring the `hudModel.ts` /
 * `gameOverModel.ts` split: the component file exports only the component
 * (fast-refresh friendly), and the logic here is unit-testable without
 * rendering or a network.
 */

import type { LeaderboardPeriod } from "../types/leaderboard";

/** One tab of the page, in display order. */
export interface LeaderboardTab {
  period: LeaderboardPeriod;
  label: string;
}

/** The two boards the backend serves (3.10/3.11), global first. */
export const LEADERBOARD_TABS: readonly LeaderboardTab[] = [
  { period: "GLOBAL", label: "Global" },
  { period: "WEEKLY", label: "Weekly" },
];

/**
 * The request path for a board. Goes through the `/api` dev-proxy prefix
 * (never a hard-coded backend origin — CLAUDE.md); `/v1` is the backend's
 * version mount, kept visible client-side so the path is honest about which
 * API version it pins.
 */
export function leaderboardPath(period: LeaderboardPeriod): string {
  return `/api/v1/leaderboard/${period === "GLOBAL" ? "global" : "weekly"}`;
}

/**
 * Attribution for a row: the first 8 hex chars of the owner's UUID. `Score`
 * carries no display name in v1 (schemas.py `LeaderboardEntry` docstring), so
 * a short opaque id is all the public board can show until profiles exist.
 */
export function formatPlayerId(userId: string): string {
  return userId.slice(0, 8);
}

/**
 * The date a score landed, as the ISO `YYYY-MM-DD` prefix — deterministic
 * across locales/timezones, which a `toLocaleDateString` rendering is not.
 */
export function formatComputedAt(computedAt: string): string {
  return computedAt.slice(0, 10);
}
