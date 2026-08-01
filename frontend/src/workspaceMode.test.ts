import { describe, expect, it } from "vitest";
import {
  DEFAULT_WORKSPACE_MODE_KEY,
  isWorkspaceMode,
  pageAfterModeSwitch,
  readWorkspaceMode,
  resolveInitialWorkspaceMode,
  workspaceHome,
  writeWorkspaceMode,
} from "./workspaceMode";

describe("workspace mode", () => {
  it("accepts only supported modes", () => {
    expect(isWorkspaceMode("market")).toBe(true);
    expect(isWorkspaceMode("research")).toBe(true);
    expect(isWorkspaceMode("trading")).toBe(false);
  });

  it("prefers the current session and falls back to the saved default", () => {
    expect(resolveInitialWorkspaceMode("research", "market")).toBe("market");
    expect(resolveInitialWorkspaceMode("research", null)).toBe("research");
    expect(resolveInitialWorkspaceMode(null, null)).toBe("market");
  });

  it("maps each mode to a distinct home", () => {
    expect(workspaceHome("market")).toBe("dashboard");
    expect(workspaceHome("research")).toBe("research-desk");
  });

  it("switches home pages while preserving active specialist pages", () => {
    expect(pageAfterModeSwitch("research-desk", "market")).toBe("dashboard");
    expect(pageAfterModeSwitch("dashboard", "research")).toBe("research-desk");
    expect(pageAfterModeSwitch("curves", "research")).toBe("curves");
    expect(pageAfterModeSwitch("bonds", "market")).toBe("bonds");
  });

  it("persists a valid preference and ignores invalid or unavailable storage", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    writeWorkspaceMode(storage, DEFAULT_WORKSPACE_MODE_KEY, "research");
    expect(readWorkspaceMode(storage, DEFAULT_WORKSPACE_MODE_KEY)).toBe("research");
    values.set(DEFAULT_WORKSPACE_MODE_KEY, "unknown");
    expect(readWorkspaceMode(storage, DEFAULT_WORKSPACE_MODE_KEY)).toBeNull();
    expect(readWorkspaceMode({ getItem: () => { throw new Error("blocked"); } }, DEFAULT_WORKSPACE_MODE_KEY)).toBeNull();
  });
});
