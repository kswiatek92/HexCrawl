import { describe, expect, it } from "vitest";
import {
  LEADERBOARD_TABS,
  formatComputedAt,
  formatPlayerId,
  leaderboardPath,
} from "./leaderboardModel";

describe("LEADERBOARD_TABS", () => {
  it("lists global then weekly — the two public boards, in display order", () => {
    expect(LEADERBOARD_TABS.map((t) => t.period)).toEqual(["GLOBAL", "WEEKLY"]);
  });
});

describe("leaderboardPath", () => {
  it("maps GLOBAL to the proxied global path", () => {
    expect(leaderboardPath("GLOBAL")).toBe("/api/v1/leaderboard/global");
  });

  it("maps WEEKLY to the proxied weekly path", () => {
    expect(leaderboardPath("WEEKLY")).toBe("/api/v1/leaderboard/weekly");
  });
});

describe("formatPlayerId", () => {
  it("truncates a UUID to its first 8 chars", () => {
    expect(formatPlayerId("a1b2c3d4-0000-0000-0000-000000000000")).toBe(
      "a1b2c3d4",
    );
  });
});

describe("formatComputedAt", () => {
  it("keeps only the ISO date prefix of a datetime", () => {
    expect(formatComputedAt("2026-07-06T21:14:03.123456Z")).toBe("2026-07-06");
  });
});
