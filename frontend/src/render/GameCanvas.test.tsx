import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GameCanvas from "./GameCanvas";
import { BACKING_HEIGHT, BACKING_WIDTH, SCALE } from "./camera";
import type { GameStateView, TileType } from "../types/gameState";

describe("GameCanvas element", () => {
  it("renders a canvas with the GBA-native backing-buffer size", () => {
    render(<GameCanvas gameState={null} />);
    const canvas = screen.getByTestId("game-canvas") as HTMLCanvasElement;
    expect(canvas.tagName).toBe("CANVAS");
    expect(canvas.width).toBe(BACKING_WIDTH); // 240
    expect(canvas.height).toBe(BACKING_HEIGHT); // 160
  });

  it("scales up with crisp (pixelated) integer scaling", () => {
    render(<GameCanvas gameState={null} />);
    const canvas = screen.getByTestId("game-canvas") as HTMLCanvasElement;
    expect(canvas.style.imageRendering).toBe("pixelated");
    expect(canvas.style.width).toBe(`${BACKING_WIDTH * SCALE}px`); // 720px
    expect(canvas.style.height).toBe(`${BACKING_HEIGHT * SCALE}px`); // 480px
  });

  it("mounts without a 2D context (jsdom default) and without game state", () => {
    expect(() => render(<GameCanvas gameState={null} />)).not.toThrow();
  });
});

// Exercising the render loop needs a 2D context, image decoding, and rAF —
// none of which jsdom provides — so we inject fakes for all three.
describe("GameCanvas render loop", () => {
  const STATE: GameStateView = {
    player: { position: [0, 0] },
    floor: {
      width: 1,
      height: 1,
      tiles: [["FLOOR"] as TileType[]],
      stairs_down: [0, 0],
    },
  };

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function installFakes() {
    const drawImage = vi.fn();
    const fillRect = vi.fn();
    const ctx = { fillStyle: "", fillRect, drawImage };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      ctx as unknown as CanvasRenderingContext2D,
    );

    // An Image whose `src` setter resolves load on the next microtask.
    class FakeImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    }
    vi.stubGlobal("Image", FakeImage);

    // Capture rAF callbacks so the test drives frames deterministically.
    const frames: FrameRequestCallback[] = [];
    const cancel = vi.fn();
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      frames.push(cb);
      return frames.length;
    });
    vi.stubGlobal("cancelAnimationFrame", cancel);

    return { ctx, drawImage, fillRect, frames, cancel };
  }

  // Let queued microtasks (image loads + the load promise) settle.
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  it("loads tiles, then draws the current state on each frame", async () => {
    const { drawImage, fillRect, frames } = installFakes();
    render(<GameCanvas gameState={STATE} />);

    await flush(); // images decode → first frame scheduled
    expect(frames.length).toBeGreaterThan(0);

    frames[frames.length - 1](0); // run one frame
    expect(fillRect).toHaveBeenCalledWith(0, 0, 240, 160); // backdrop cleared
    expect(drawImage).toHaveBeenCalledTimes(1); // the single FLOOR tile
  });

  it("cancels the animation frame on unmount", async () => {
    const { cancel } = installFakes();
    const { unmount } = render(<GameCanvas gameState={STATE} />);
    await flush();
    unmount();
    expect(cancel).toHaveBeenCalled();
  });
});
