import "@testing-library/jest-dom/vitest";

// jsdom has no canvas 2D context — calling getContext logs a noisy
// "Not implemented" error. Default it to null so components that probe for a
// context (GameCanvas) bail cleanly; tests that need a real context spy on this
// and return a fake.
HTMLCanvasElement.prototype.getContext = (() =>
  null) as typeof HTMLCanvasElement.prototype.getContext;
