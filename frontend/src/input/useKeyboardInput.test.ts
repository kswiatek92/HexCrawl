import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { keyToAction, useKeyboardInput } from "./useKeyboardInput";
import type { ClientAction } from "../types/socket";

/**
 * Dispatch a real `keydown` on a target (default `window`) and return the event
 * so a test can assert on `defaultPrevented`. `cancelable`/`bubbles` are on so
 * `preventDefault` is observable and an event fired at a child still reaches the
 * window listener with its `target` intact.
 */
function pressKey(
  key: string,
  init: KeyboardEventInit = {},
  target: EventTarget = window,
): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key,
    cancelable: true,
    bubbles: true,
    ...init,
  });
  act(() => {
    target.dispatchEvent(event);
  });
  return event;
}

describe("keyToAction", () => {
  it.each([
    ["ArrowUp", "NORTH"],
    ["w", "NORTH"],
    ["W", "NORTH"],
    ["ArrowDown", "SOUTH"],
    ["s", "SOUTH"],
    ["S", "SOUTH"],
    ["ArrowLeft", "WEST"],
    ["a", "WEST"],
    ["A", "WEST"],
    ["ArrowRight", "EAST"],
    ["d", "EAST"],
    ["D", "EAST"],
  ])("maps %s to move %s", (key, direction) => {
    expect(keyToAction(key)).toEqual({ action: "move", direction });
  });

  it("maps space to wait", () => {
    expect(keyToAction(" ")).toEqual({ action: "wait" });
  });

  it.each(["q", "Enter", "Shift", "Escape", ""])(
    "leaves unbound key %o unmapped",
    (key) => {
      expect(keyToAction(key)).toBeNull();
    },
  );
});

describe("useKeyboardInput", () => {
  afterEach(() => {
    // Each renderHook auto-unmounts, but guard against a leaked listener.
    vi.restoreAllMocks();
  });

  it("sends the mapped action on a bound keydown", () => {
    const sendAction = vi.fn<(action: ClientAction) => void>();
    renderHook(() => useKeyboardInput(sendAction));

    pressKey("ArrowLeft");

    expect(sendAction).toHaveBeenCalledTimes(1);
    expect(sendAction).toHaveBeenCalledWith({
      action: "move",
      direction: "WEST",
    });
  });

  it("calls preventDefault on a bound key so the page doesn't scroll", () => {
    renderHook(() => useKeyboardInput(vi.fn()));

    const event = pressKey(" ");

    expect(event.defaultPrevented).toBe(true);
  });

  it("ignores an unbound key (no send, no preventDefault)", () => {
    const sendAction = vi.fn();
    renderHook(() => useKeyboardInput(sendAction));

    const event = pressKey("q");

    expect(sendAction).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("drops OS key-repeat so a held key fires once", () => {
    const sendAction = vi.fn();
    renderHook(() => useKeyboardInput(sendAction));

    pressKey("ArrowUp", { repeat: true });

    expect(sendAction).not.toHaveBeenCalled();
  });

  it("ignores keys typed into an editable element", () => {
    const sendAction = vi.fn();
    renderHook(() => useKeyboardInput(sendAction));

    const input = document.createElement("input");
    document.body.appendChild(input);
    pressKey("w", {}, input); // bubbles to the window listener with target=input
    input.remove();

    expect(sendAction).not.toHaveBeenCalled();
  });

  it("attaches no listener when disabled", () => {
    const sendAction = vi.fn();
    renderHook(() => useKeyboardInput(sendAction, { enabled: false }));

    pressKey("ArrowUp");

    expect(sendAction).not.toHaveBeenCalled();
  });

  it("detaches the listener on unmount", () => {
    const sendAction = vi.fn();
    const { unmount } = renderHook(() => useKeyboardInput(sendAction));

    unmount();
    pressKey("ArrowUp");

    expect(sendAction).not.toHaveBeenCalled();
  });

  it("calls the latest sendAction after a rerender (no stale closure)", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ fn }) => useKeyboardInput(fn), {
      initialProps: { fn: first as (action: ClientAction) => void },
    });

    rerender({ fn: second as (action: ClientAction) => void });
    pressKey("ArrowDown");

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith({ action: "move", direction: "SOUTH" });
  });
});
