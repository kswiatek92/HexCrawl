import "@testing-library/jest-dom/vitest";

// jsdom has no canvas 2D context — calling getContext logs a noisy
// "Not implemented" error. Default it to null so components that probe for a
// context (GameCanvas) bail cleanly; tests that need a real context spy on this
// and return a fake.
HTMLCanvasElement.prototype.getContext = (() =>
  null) as typeof HTMLCanvasElement.prototype.getContext;

// jsdom has no ResizeObserver (GameCanvas uses one for largest-fit scaling).
// An inert observer is enough: jsdom never lays out, so there are no real
// resizes to report — tests that exercise scaling mock getBoundingClientRect
// and rely on the component's mount-time measure instead.
class InertResizeObserver implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= InertResizeObserver;
