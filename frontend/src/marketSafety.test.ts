import { describe, expect, it } from "vitest";
import { canWatchItem } from "./marketSafety";

describe("market safety", () => {
  it("blocks missing identifiers and quarantined rows from watchlists", () => {
    expect(canWatchItem("", "trusted")).toBe(false);
    expect(canWatchItem("  ", "partial")).toBe(false);
    expect(canWatchItem("240011", "suspicious")).toBe(false);
    expect(canWatchItem("240011", "trusted")).toBe(true);
  });
});
