import { describe, expect, it } from "vitest";
import {
  PLAYER_BOB_OFFSETS_PX,
  PLAYER_FRAME_COUNT,
  PLAYER_FRAME_DURATION_MS,
  bobOffsetForFrame,
} from "./playerAnimation";

describe("player animation constants", () => {
  it("is a two-frame up/down bob held on a positive cadence", () => {
    expect([...PLAYER_BOB_OFFSETS_PX]).toEqual([0, -1]);
    expect(PLAYER_FRAME_COUNT).toBe(2);
    expect(PLAYER_FRAME_DURATION_MS).toBeGreaterThan(0);
  });
});

describe("bobOffsetForFrame", () => {
  it("maps each frame to its bob offset", () => {
    expect(bobOffsetForFrame(0)).toBe(0);
    expect(bobOffsetForFrame(1)).toBe(-1);
  });

  it("wraps a monotonically increasing counter modulo the frame count", () => {
    expect(bobOffsetForFrame(2)).toBe(0); // back to frame 0
    expect(bobOffsetForFrame(3)).toBe(-1);
    expect(bobOffsetForFrame(100)).toBe(0); // even → frame 0
  });

  it("handles a negative frame index without going out of bounds", () => {
    expect(bobOffsetForFrame(-1)).toBe(-1);
  });
});
