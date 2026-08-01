import { describe, expect, it } from "vitest";
import { shouldForceSovereignRefresh } from "./sovereignUtils";

describe("sovereign refresh behavior", () => {
  it("consumes a manual refresh without forcing later filter changes", () => {
    expect(shouldForceSovereignRefresh(0, 0)).toBe(false);
    expect(shouldForceSovereignRefresh(1, 0)).toBe(true);
    expect(shouldForceSovereignRefresh(1, 1)).toBe(false);
    expect(shouldForceSovereignRefresh(2, 1)).toBe(true);
  });
});
