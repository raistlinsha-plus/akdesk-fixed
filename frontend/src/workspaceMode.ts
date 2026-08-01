export type WorkspaceMode = "market" | "research";

export const DEFAULT_WORKSPACE_MODE_KEY = "akdesk.default-workspace-mode";
export const SESSION_WORKSPACE_MODE_KEY = "akdesk.session-workspace-mode";

export function isWorkspaceMode(value: unknown): value is WorkspaceMode {
  return value === "market" || value === "research";
}

export function readWorkspaceMode(
  storage: Pick<Storage, "getItem"> | undefined,
  key: string,
): WorkspaceMode | null {
  if (!storage) return null;
  try {
    const value = storage.getItem(key);
    return isWorkspaceMode(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeWorkspaceMode(
  storage: Pick<Storage, "setItem"> | undefined,
  key: string,
  mode: WorkspaceMode,
): void {
  if (!storage) return;
  try {
    storage.setItem(key, mode);
  } catch {
    // Storage can be unavailable in private or hardened browser contexts.
  }
}

export function resolveInitialWorkspaceMode(
  defaultMode: WorkspaceMode | null,
  sessionMode: WorkspaceMode | null,
): WorkspaceMode {
  return sessionMode ?? defaultMode ?? "market";
}

export function workspaceHome(mode: WorkspaceMode): "dashboard" | "research-desk" {
  return mode === "market" ? "dashboard" : "research-desk";
}

export function pageAfterModeSwitch(
  currentPage: string,
  nextMode: WorkspaceMode,
): string {
  if (currentPage === "dashboard" || currentPage === "research-desk") {
    return workspaceHome(nextMode);
  }
  return currentPage;
}
