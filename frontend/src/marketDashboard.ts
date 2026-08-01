export const DASHBOARD_MODULES = [
  "curve",
  "futures",
  "bonds",
  "events",
  "fx",
] as const;

export type DashboardModule = (typeof DASHBOARD_MODULES)[number];

export const DASHBOARD_MODULE_LABELS: Record<DashboardModule, string> = {
  curve: "收益率曲线",
  futures: "国债期货",
  bonds: "活跃现券",
  events: "重要事件",
  fx: "跨市场外汇",
};

export const DASHBOARD_MODULES_KEY = "akdesk.market-dashboard.modules";
export const RECENT_MARKET_PAGES_KEY = "akdesk.recent-market-pages";

export const DASHBOARD_PRESETS: Record<string, DashboardModule[]> = {
  全景: [...DASHBOARD_MODULES],
  利率优先: ["curve", "futures", "bonds", "events"],
  跨市场: ["curve", "futures", "fx", "events"],
};

export function parseDashboardModules(raw: string | null): DashboardModule[] {
  if (!raw) return [...DASHBOARD_MODULES];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [...DASHBOARD_MODULES];
    const valid = Array.from(
      new Set(parsed.filter((item): item is DashboardModule =>
        DASHBOARD_MODULES.includes(item as DashboardModule))),
    );
    return valid.length ? valid : [...DASHBOARD_MODULES];
  } catch {
    return [...DASHBOARD_MODULES];
  }
}

export function readDashboardModules(
  storage: Pick<Storage, "getItem"> | undefined,
): DashboardModule[] {
  if (!storage) return [...DASHBOARD_MODULES];
  try {
    return parseDashboardModules(storage.getItem(DASHBOARD_MODULES_KEY));
  } catch {
    return [...DASHBOARD_MODULES];
  }
}

export function writeDashboardModules(
  storage: Pick<Storage, "setItem"> | undefined,
  modules: DashboardModule[],
): void {
  if (!storage) return;
  try {
    storage.setItem(DASHBOARD_MODULES_KEY, JSON.stringify(modules));
  } catch {
    // Local preferences are optional in hardened browser contexts.
  }
}

export function percentileRank(
  values: Array<number | null>,
  target?: number | null,
): number | null {
  const valid = values.filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
  const latest = target ?? valid[valid.length - 1];
  if (!valid.length || latest == null || !Number.isFinite(latest)) return null;
  const atOrBelow = valid.filter((value) => value <= latest).length;
  return Math.round((atOrBelow / valid.length) * 100);
}

export interface RecentMarketPage {
  id: string;
  label: string;
  visitedAt: string;
}

export function parseRecentMarketPages(raw: string | null): RecentMarketPage[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is RecentMarketPage => Boolean(
      item && typeof item === "object"
      && "id" in item && typeof item.id === "string"
      && "label" in item && typeof item.label === "string"
      && "visitedAt" in item && typeof item.visitedAt === "string",
    )).slice(0, 5);
  } catch {
    return [];
  }
}

export function recordRecentMarketPage(
  storage: Pick<Storage, "getItem" | "setItem"> | undefined,
  id: string,
  label: string,
  visitedAt = new Date().toISOString(),
): RecentMarketPage[] {
  if (!storage || id === "dashboard") return [];
  const next = [
    { id, label, visitedAt },
    ...parseRecentMarketPages(storage.getItem(RECENT_MARKET_PAGES_KEY))
      .filter((item) => item.id !== id),
  ].slice(0, 5);
  try {
    storage.setItem(RECENT_MARKET_PAGES_KEY, JSON.stringify(next));
  } catch {
    return next;
  }
  return next;
}

export function readRecentMarketPages(
  storage: Pick<Storage, "getItem"> | undefined,
): RecentMarketPage[] {
  if (!storage) return [];
  try {
    return parseRecentMarketPages(storage.getItem(RECENT_MARKET_PAGES_KEY));
  } catch {
    return [];
  }
}
