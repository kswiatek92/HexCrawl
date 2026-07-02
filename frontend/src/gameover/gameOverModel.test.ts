import { describe, expect, it } from "vitest";
import { gameOverSubtitle, gameOverTitle } from "./gameOverModel";

describe("gameOverTitle", () => {
  it("names a death GAME OVER and an abandonment RUN ABANDONED", () => {
    expect(gameOverTitle("died")).toBe("GAME OVER");
    expect(gameOverTitle("abandoned")).toBe("RUN ABANDONED");
  });
});

describe("gameOverSubtitle", () => {
  it("gives each ending its own epitaph", () => {
    expect(gameOverSubtitle("died")).not.toBe(gameOverSubtitle("abandoned"));
    // The abandoned line carries the no-score rule (task 3.3).
    expect(gameOverSubtitle("abandoned")).toContain("No score");
  });
});
