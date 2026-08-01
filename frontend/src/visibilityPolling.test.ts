import { afterEach, describe, expect, it, vi } from "vitest";
import {
  startVisibilityPolling,
  type VisibilityPollingTarget,
} from "./visibilityPolling";

class FakeVisibilityTarget implements VisibilityPollingTarget {
  visibilityState: DocumentVisibilityState = "visible";
  private listeners = new Set<EventListener>();

  addEventListener(_type: "visibilitychange", listener: EventListener) {
    this.listeners.add(listener);
  }

  removeEventListener(_type: "visibilitychange", listener: EventListener) {
    this.listeners.delete(listener);
  }

  changeTo(state: DocumentVisibilityState) {
    this.visibilityState = state;
    for (const listener of this.listeners) listener(new Event("visibilitychange"));
  }
}

afterEach(() => {
  vi.useRealTimers();
});

describe("visibility-aware polling", () => {
  it("pauses in the background and refreshes immediately on return", () => {
    vi.useFakeTimers();
    const target = new FakeVisibilityTarget();
    const callback = vi.fn();
    const stop = startVisibilityPolling(callback, 10_000, target);

    vi.advanceTimersByTime(10_000);
    expect(callback).toHaveBeenCalledTimes(1);

    target.changeTo("hidden");
    vi.advanceTimersByTime(60_000);
    expect(callback).toHaveBeenCalledTimes(1);

    target.changeTo("visible");
    expect(callback).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(10_000);
    expect(callback).toHaveBeenCalledTimes(3);

    stop();
    vi.advanceTimersByTime(20_000);
    expect(callback).toHaveBeenCalledTimes(3);
  });
});
