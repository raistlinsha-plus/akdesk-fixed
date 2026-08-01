import { describe, expect, it } from "vitest";
import {
  parseDashboardModules,
  percentileRank,
  recordRecentMarketPage,
} from "./marketDashboard";

describe("market dashboard preferences", () => {
  it("repairs invalid module preferences", () => {
    expect(parseDashboardModules('["curve","bad","curve","fx"]')).toEqual(["curve", "fx"]);
    expect(parseDashboardModules("broken")).toContain("bonds");
  });

  it("calculates a transparent historical percentile", () => {
    expect(percentileRank([1, 2, 3, 4], 3)).toBe(75);
    expect(percentileRank([null, null])).toBeNull();
  });

  it("keeps the five most recent distinct market pages", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    recordRecentMarketPage(storage, "money", "资金面", "2026-07-17T10:00:00");
    recordRecentMarketPage(storage, "curves", "收益率曲线", "2026-07-17T11:00:00");
    const next = recordRecentMarketPage(storage, "money", "资金面", "2026-07-17T12:00:00");
    expect(next.map((item) => item.id)).toEqual(["money", "curves"]);
  });
});
